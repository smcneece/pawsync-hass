"""Switch platform for Pawsync devices.

Each switch is described by a PawsyncSwitchEntityDescription with two callables:
  value_fn(device) -> bool   reads current state from deviceProp
  cmd_fn(on, device) -> (method, data)  builds the bypassV2 payload

The device argument is passed to cmd_fn so context-sensitive switches (like
Sleep Mode, which must include start/end times) can read existing values from
deviceProp rather than hardcoding defaults.

Optimistic state: _attr_is_on is set immediately on a successful command so the
UI doesn't snap back. _handle_coordinator_update overwrites it with the real
device value on the next poll to confirm (or correct) the change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import aiohttp
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import DOMAIN, PAWSYNC_COORDINATOR

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PawsyncSwitchEntityDescription(SwitchEntityDescription):
    value_fn: Callable[[pawsync.Device], bool | None] = None
    cmd_fn: Callable[[bool, pawsync.Device], tuple[str, dict]] = None  # returns (api_method, data)


SWITCH_TYPES: tuple[PawsyncSwitchEntityDescription, ...] = (
    PawsyncSwitchEntityDescription(
        key="intelligent_feeding",
        name="Smart feeding",
        icon="mdi:brain",
        value_fn=lambda d: d.deviceProp.get("intelligentFeedingSwitch") == 1,
        cmd_fn=lambda on, d: ("setIntelligentFeedingMode", {"enable": 1 if on else 0}),
    ),
    PawsyncSwitchEntityDescription(
        key="slow_feed",
        name="Slow Feeding",
        icon="mdi:speedometer-slow",
        value_fn=lambda d: d.deviceProp.get("slowFeedSwitch") == 1,
        cmd_fn=lambda on, d: ("setPetSlowFeedMode", {"enable": 1 if on else 0}),
    ),
    PawsyncSwitchEntityDescription(
        key="accurate_feeding",
        name="Precision mode",
        icon="mdi:target",
        value_fn=lambda d: d.deviceProp.get("accurateFeeding") == 1,
        # Note the capital I in setIAccurateFeedingMode — confirmed via mitmproxy sniff.
        cmd_fn=lambda on, d: ("setIAccurateFeedingMode", {"enable": 1 if on else 0}),
    ),
    PawsyncSwitchEntityDescription(
        key="sleep_mode",
        name="Sleep Mode",
        icon="mdi:sleep",
        value_fn=lambda d: (d.deviceProp.get("sleepMode") or {}).get("enable") == 1,
        cmd_fn=lambda on, d: ("setPetSleepMode", {
            "enable": 1 if on else 0,
            # Must send existing times alongside enable or device silently rejects the command.
            "startClkSec": (d.deviceProp.get("sleepMode") or {}).get("startClkSec", 79200),
            "endClkSec": (d.deviceProp.get("sleepMode") or {}).get("endClkSec", 32400),
        }),
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
            PawsyncDeviceSwitch(coordinator, d, desc, session)
            for d in coordinator.data["devices"]
            for desc in SWITCH_TYPES
            if f"{d.deviceId}_{desc.key}" not in known_ids
        ]
        if new_entities:
            known_ids.update(f"{e.device.deviceId}_{e.entity_description.key}" for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncDeviceSwitch(CoordinatorEntity, SwitchEntity):

    entity_description: PawsyncSwitchEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncSwitchEntityDescription, session: aiohttp.ClientSession):
        super().__init__(coordinator)
        self.device = device
        self.entity_description = description
        self._session = session
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"
        self._attr_icon = description.icon
        self._attr_name = f"{device.deviceName} {description.name}"
        self._attr_extra_state_attributes = {"device_id": device.deviceId}
        self._attr_is_on = description.value_fn(device) if description.value_fn else None

    @callback
    def _handle_coordinator_update(self) -> None:
        for d in (self.coordinator.data or {}).get("devices", []):
            if d.deviceId == self.device.deviceId:
                self.device = d
                break
        if self.entity_description.value_fn:
            self._attr_is_on = self.entity_description.value_fn(self.device)
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.device.deviceId)},
            "name": self.device.deviceName,
            "model": self.device.deviceModel,
            "manufacturer": "Pawsync",
            "hw_version": self.device.configModel,
        }

    async def _send_command(self, on: bool) -> None:
        method, data = self.entity_description.cmd_fn(on, self.device)
        response = await self.device.setSwitch(self._session, method, data)
        resp_json = await response.json()
        if resp_json.get("code") != 0:
            _LOGGER.error("Switch %s=%s failed for %s: %s", method, on, self.device.deviceId, resp_json)
            return
        _LOGGER.debug("Switch %s=%s successful for %s", method, on, self.device.deviceId)
        self._attr_is_on = on
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command(False)
