"""Number platform for Pawsync devices — hopper food level.

The app lets you record the hopper fill level (1.0–3.6L) after refilling so the
server can estimate days of food remaining. The API call is updatePetContentSize
with volume_ml. The server responds with daysRemain and contentInPot (percentage).

contentInPot in deviceProp is the hopper fill percentage (0–100), which we convert
back to ml for the slider: pct / 100 * 3600. This lets the slider reflect the
current level rather than always starting at zero.
"""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import DOMAIN, PAWSYNC_COORDINATOR

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
            PawsyncHopperLevel(coordinator, d, session)
            for d in coordinator.data["devices"]
            if d.deviceId not in known_ids
        ]
        if new_entities:
            known_ids.update(e._device_id for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncHopperLevel(CoordinatorEntity, NumberEntity):

    _attr_icon = "mdi:silo"
    _attr_native_min_value = 1000
    _attr_native_max_value = 3600
    _attr_native_step = 100
    _attr_native_unit_of_measurement = UnitOfVolume.MILLILITERS
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, device: pawsync.Device, session: aiohttp.ClientSession):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._session = session
        self._attr_unique_id = f"pawsync_{device.deviceId}_hopper_level"
        self._attr_name = f"{device.deviceName} Hopper level"

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

    @property
    def native_value(self) -> float | None:
        d = self._device
        if d is None:
            return None
        pct = d.deviceProp.get("contentInPot")
        if pct is None:
            return None
        return round(pct / 100 * 3600)

    async def async_set_native_value(self, value: float) -> None:
        d = self._device
        if d is None:
            return
        response = await d.setSwitch(self._session, "updatePetContentSize", {
            "type": 0,
            "volume_ml": float(value),
        })
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            _LOGGER.error("updatePetContentSize failed for %s: %s", self._device_id, resp_json)
        else:
            _LOGGER.debug("Hopper level set to %sml for %s", value, self._device_id)
            await self.coordinator.async_request_refresh()
