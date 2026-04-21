"""Button platform for Pawsync devices.

Each button has a press_fn(device, session, coordinator) coroutine. The Refresh
button is special — press_fn=None signals async_press to call coordinator refresh
instead of making an API call. All other buttons trigger a coordinator refresh
after a successful API call so sensors update immediately.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import aiohttp
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE, DOMAIN, PAWSYNC_COORDINATOR

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PawsyncButtonEntityDescription(ButtonEntityDescription):
    press_fn: Callable[[pawsync.Device, aiohttp.ClientSession, Any], Coroutine] | None = None


BUTTON_TYPES: tuple[PawsyncButtonEntityDescription, ...] = (
    PawsyncButtonEntityDescription(
        key="refresh",
        name="Refresh",
        icon="mdi:refresh",
        press_fn=None,  # handled specially in async_press
    ),
    PawsyncButtonEntityDescription(
        key="feed",
        name="Extra Meal",
        icon="mdi:food-variant",
        press_fn=lambda d, s, coord: d.requestFeed(
            s, int(coord.config_entry.options.get(CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE))
        ),
    ),
    PawsyncButtonEntityDescription(
        key="zero_scale",
        name="Zero Scale",
        icon="mdi:scale-balance",
        press_fn=lambda d, s, coord: d.zeroScale(s),
    ),
    PawsyncButtonEntityDescription(
        key="meal_call",
        name="Meal Call",
        icon="mdi:bullhorn",
        press_fn=lambda d, s, coord: d.playMealCall(s),
    ),
    PawsyncButtonEntityDescription(
        key="reset_desiccant",
        name="Reset Desiccant",
        icon="mdi:air-filter",
        press_fn=lambda d, s, coord: d.resetDesiccant(s),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][PAWSYNC_COORDINATOR]
    session = hass.data[DOMAIN][entry.entry_id]["session"]
    known_ids: set[str] = set()

    @callback
    def _check_for_new() -> None:
        if not coordinator.data:
            return
        new_entities = [
            PawsyncButton(coordinator, d, desc, session)
            for d in coordinator.data["devices"]
            for desc in BUTTON_TYPES
            if f"{d.deviceId}_{desc.key}" not in known_ids
        ]
        if new_entities:
            known_ids.update(f"{e._device_id}_{e.entity_description.key}" for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncButton(CoordinatorEntity, ButtonEntity):

    entity_description: PawsyncButtonEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncButtonEntityDescription, session: aiohttp.ClientSession):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._session = session
        self.entity_description = description
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"
        self._attr_name = f"{device.deviceName} {description.name}"
        self._attr_icon = description.icon

    @property
    def _device(self) -> pawsync.Device | None:
        if not self.coordinator.data:
            return None
        return next((d for d in self.coordinator.data["devices"] if d.deviceId == self._device_id), None)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._device is not None

    @property
    def device_info(self):
        d = self._device
        if d is None:
            return None
        return {
            "identifiers": {(DOMAIN, d.deviceId)},
            "name": d.deviceName,
            "model": d.deviceModel,
            "manufacturer": "Pawsync",
            "hw_version": d.configModel,
        }

    async def async_press(self) -> None:
        if self.entity_description.press_fn is None:
            await self.coordinator.async_request_refresh()
            return
        device = self._device
        if device is None:
            _LOGGER.error("Device %s not found during button press (%s)", self._device_id, self.entity_description.key)
            return
        response = await self.entity_description.press_fn(device, self._session, self.coordinator)
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            _LOGGER.error("%s failed for %s: %s", self.entity_description.key, self._device_id, resp_json)
        else:
            _LOGGER.info("%s successful for %s", self.entity_description.key, self._device_id)
            await self.coordinator.async_request_refresh()
