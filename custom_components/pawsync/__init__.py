from __future__ import annotations

from datetime import timedelta
import logging

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import pawsync
from .const import CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE, DEFAULT_UPDATE_INTERVAL, DOMAIN, PAWSYNC_COORDINATOR, PLATFORMS

logger = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            })
    },
    extra=vol.ALLOW_EXTRA
)

all_devices: dict[str, pawsync.Device] = {}
sessions: dict[str, aiohttp.ClientSession] = {}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=config[DOMAIN],
            )
        )

    async def handle_feed(call: ServiceCall):
        entity_id = call.data.get("entity_id")
        amount = int(call.data.get("amount", DEFAULT_MEAL_SIZE))
        if entity_id is None:
            return
        entity = hass.states.get(entity_id)
        if entity is None:
            logger.error("Entity %s not found", entity_id)
            return
        device_id = entity.attributes.get("device_id")
        if device_id is None:
            logger.error("No device_id attribute on %s", entity_id)
            return

        logger.info("Feed requested: entity=%s device=%s amount=%s", entity_id, device_id, amount)

        device = all_devices.get(device_id)
        session = sessions.get(device_id)
        if device is None or session is None:
            logger.error("Device %s not in registry — has it loaded yet?", device_id)
            return

        response = await device.requestFeed(session, amount)
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            logger.error("Feed failed for device %s: %s", device_id, resp_json)

    SERVICE_FEED_SCHEMA = vol.Schema({
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("amount", default=DEFAULT_MEAL_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
    })
    hass.services.async_register(DOMAIN, "feed", handle_feed, schema=SERVICE_FEED_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = async_get_clientsession(hass)
    await pawsync.login(session, username, password)

    update_interval = int(entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL))

    async def async_update():
        devices = await pawsync.getDeviceList(session, logger)
        if not devices:
            try:
                await pawsync.login(session, username, password)
            except pawsync.PawsyncAuthError as err:
                raise UpdateFailed(f"Re-authentication failed: {err}") from err
            devices = await pawsync.getDeviceList(session, logger)
            if not devices:
                raise UpdateFailed("Could not retrieve device list after re-auth")

        for d in devices:
            sessions[d.deviceId] = session
            all_devices[d.deviceId] = d

        return devices

    coordinator = DataUpdateCoordinator(
        hass,
        logger,
        name="pawsync-update",
        update_interval=timedelta(minutes=update_interval),
        update_method=async_update,
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        PAWSYNC_COORDINATOR: coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry when options change so the coordinator picks up new settings
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        coordinator = entry_data.get(PAWSYNC_COORDINATOR)
        if coordinator and coordinator.data:
            for device in coordinator.data:
                all_devices.pop(device.deviceId, None)
                sessions.pop(device.deviceId, None)
    return unload_ok
