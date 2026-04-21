from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import pawsync
from .const import (
    CONF_MEAL_SIZE, CONF_UNIT_SYSTEM,
    DEFAULT_MEAL_SIZE, DEFAULT_UPDATE_INTERVAL,
    DOMAIN, UNIT_IMPERIAL, UNIT_METRIC,
)

_LOGGER = logging.getLogger(__name__)


class PawsyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                session = async_get_clientsession(self.hass)
                await pawsync.login(
                    session,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )
            except pawsync.PawsyncAuthError:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Unexpected error during setup: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_import(self, import_data):
        return await self.async_step_user(import_data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PawsyncOptionsFlowHandler(config_entry)


class PawsyncOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        pass  # self.config_entry is injected by HA framework

    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            new_username = user_input[CONF_USERNAME].strip()
            new_password = user_input[CONF_PASSWORD].strip()

            # Validate credentials if either changed
            current_username = self.config_entry.data[CONF_USERNAME]
            current_password = self.config_entry.data[CONF_PASSWORD]
            credentials_changed = (new_username != current_username or new_password != current_password)

            if credentials_changed:
                try:
                    session = async_get_clientsession(self.hass)
                    await pawsync.login(session, new_username, new_password)
                except pawsync.PawsyncAuthError:
                    errors["base"] = "invalid_auth"
                except Exception as err:
                    _LOGGER.exception("Unexpected error validating credentials: %s", err)
                    errors["base"] = "unknown"

            if not errors:
                if credentials_changed:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        title=new_username,
                        data={**self.config_entry.data, CONF_USERNAME: new_username, CONF_PASSWORD: new_password},
                    )
                return self.async_create_entry(title="", data={
                    CONF_MEAL_SIZE: user_input[CONF_MEAL_SIZE],
                    "update_interval": user_input["update_interval"],
                    CONF_UNIT_SYSTEM: user_input[CONF_UNIT_SYSTEM],
                })

        current_username = self.config_entry.data[CONF_USERNAME]
        current_password = self.config_entry.data[CONF_PASSWORD]
        current_meal_size = self.config_entry.options.get(CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE)
        current_interval = self.config_entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)
        current_units = self.config_entry.options.get(CONF_UNIT_SYSTEM, UNIT_IMPERIAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME, default=current_username): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD, default=current_password): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_UNIT_SYSTEM, default=current_units): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": UNIT_IMPERIAL, "label": "US (oz)"},
                            {"value": UNIT_METRIC, "label": "Metric (g)"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_MEAL_SIZE, default=current_meal_size): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=11,
                        max=110,
                        step=11,
                        unit_of_measurement="g",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required("update_interval", default=current_interval): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=60,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }),
            errors=errors,
        )
