"""Time platform for Pawsync devices — sleep mode schedule.

Exposes sleep mode start and end times as HA time entities with a time picker UI.
Changing either entity sends the full setPetSleepMode payload (enable + both times)
because the device requires all three fields together.

Times are stored on the device as seconds since midnight (startClkSec/endClkSec).
These entities enable per-day scheduling via HA automations even though the device
itself only stores a single schedule.
"""

from __future__ import annotations

import logging
from datetime import time

import aiohttp
from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import DOMAIN, PAWSYNC_COORDINATOR

_LOGGER = logging.getLogger(__name__)


def _secs_to_time(secs: int) -> time:
    return time(hour=(secs // 3600) % 24, minute=(secs % 3600) // 60)


def _time_to_secs(t: time) -> int:
    return t.hour * 3600 + t.minute * 60


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
        new_entities = []
        for d in coordinator.data["devices"]:
            for key, name in (("sleep_start", "Sleep Mode 1 Start"), ("sleep_end", "Sleep Mode 2 End")):
                uid = f"{d.deviceId}_{key}"
                if uid not in known_ids:
                    new_entities.append(PawsyncSleepTime(coordinator, d, key, name, session))
                    known_ids.add(uid)
        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncSleepTime(CoordinatorEntity, TimeEntity):

    def __init__(self, coordinator, device: pawsync.Device, key: str, name: str, session: aiohttp.ClientSession):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._key = key
        self._session = session
        self._attr_unique_id = f"pawsync_{device.deviceId}_{key}"
        self._attr_name = f"{device.deviceName} {name}"
        self._attr_icon = "mdi:clock-time-eight-outline"

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
    def native_value(self) -> time | None:
        d = self._device
        if d is None:
            return None
        sleep = d.deviceProp.get("sleepMode") or {}
        prop = "startClkSec" if self._key == "sleep_start" else "endClkSec"
        secs = sleep.get(prop)
        return _secs_to_time(secs) if secs is not None else None

    async def async_set_value(self, value: time) -> None:
        d = self._device
        if d is None:
            return
        sleep = d.deviceProp.get("sleepMode") or {}
        if self._key == "sleep_start":
            start_secs = _time_to_secs(value)
            end_secs = sleep.get("endClkSec", 32400)
        else:
            start_secs = sleep.get("startClkSec", 79200)
            end_secs = _time_to_secs(value)

        response = await d.setSwitch(self._session, "setPetSleepMode", {
            "enable": sleep.get("enable", 1),
            "startClkSec": start_secs,
            "endClkSec": end_secs,
        })
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            _LOGGER.error("setPetSleepMode time update failed for %s: %s", self._device_id, resp_json)
        else:
            _LOGGER.debug("Sleep mode schedule updated for %s", self._device_id)
            await self.coordinator.async_request_refresh()
