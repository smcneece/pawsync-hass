"""Button platform for Pawsync devices — one Feed Now button per feeder."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE, DOMAIN, PAWSYNC_COORDINATOR

_LOGGER = logging.getLogger(__name__)


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
            PawsyncFeedButton(coordinator, d, session)
            for d in coordinator.data
            if d.deviceId not in known_ids
        ]
        if new_entities:
            known_ids.update(e._device_id for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncFeedButton(CoordinatorEntity, ButtonEntity):

    def __init__(self, coordinator, device: pawsync.Device, session: aiohttp.ClientSession):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._session = session
        self._attr_unique_id = f"pawsync_{device.deviceId}_feed"
        self._attr_name = f"{device.deviceName} Feed Now"
        self._attr_icon = "mdi:food-variant"

    @property
    def _device(self) -> pawsync.Device | None:
        if not self.coordinator.data:
            return None
        return next((d for d in self.coordinator.data if d.deviceId == self._device_id), None)

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
        device = self._device
        if device is None:
            _LOGGER.error("Device %s not found during feed press", self._device_id)
            return

        # Read meal size from options at press time so option changes take effect immediately
        amount = int(self.coordinator.config_entry.options.get(CONF_MEAL_SIZE, DEFAULT_MEAL_SIZE))

        response = await device.requestFeed(self._session, amount)
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            _LOGGER.error("Feed failed for %s: %s", self._device_id, resp_json)
        else:
            _LOGGER.info("Feed successful for %s (amount=%s)", self._device_id, amount)
