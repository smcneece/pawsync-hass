"""Binary sensor platform for Pawsync devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import DOMAIN, PAWSYNC_COORDINATOR

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PawsyncBinarySensorEntityDescription(BinarySensorEntityDescription):
    value_fn: Callable[[pawsync.Device], Any] | None = None


BINARY_SENSOR_TYPES: tuple[PawsyncBinarySensorEntityDescription, ...] = (
    PawsyncBinarySensorEntityDescription(
        key="power_adapter",
        name="Power adapter",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: d.deviceProp.get("powerAdapter") == 1,
    ),
    PawsyncBinarySensorEntityDescription(
        key="intelligent_feeding",
        name="Intelligent feeding",
        icon="mdi:robot-pet",
        value_fn=lambda d: d.deviceProp.get("intelligentFeedingSwitch") == 1,
    ),
    PawsyncBinarySensorEntityDescription(
        key="slow_feed",
        name="Slow feed",
        icon="mdi:speedometer-slow",
        value_fn=lambda d: d.deviceProp.get("slowFeedSwitch") == 1,
    ),
    PawsyncBinarySensorEntityDescription(
        key="accurate_feeding",
        name="Accurate feeding",
        icon="mdi:target",
        value_fn=lambda d: d.deviceProp.get("accurateFeeding") == 1,
    ),
    PawsyncBinarySensorEntityDescription(
        key="sleep_mode",
        name="Sleep mode",
        icon="mdi:sleep",
        value_fn=lambda d: (d.deviceProp.get("sleepMode") or {}).get("enable") == 1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][PAWSYNC_COORDINATOR]
    known_ids: set[str] = set()

    @callback
    def _check_for_new() -> None:
        if not coordinator.data:
            return
        new_entities = [
            PawsyncDeviceBinarySensor(coordinator, d, desc)
            for d in coordinator.data
            for desc in BINARY_SENSOR_TYPES
            if f"{d.deviceId}_{desc.key}" not in known_ids
        ]
        if new_entities:
            known_ids.update(f"{e.device.deviceId}_{e.entity_description.key}" for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncDeviceBinarySensor(CoordinatorEntity, BinarySensorEntity):

    entity_description: PawsyncBinarySensorEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncBinarySensorEntityDescription):
        super().__init__(coordinator)
        self.device = device
        self.entity_description = description
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"
        self._attr_name = f"{device.deviceName} {description.name}"
        self._attr_extra_state_attributes = {"device_id": device.deviceId}

    @callback
    def _handle_coordinator_update(self) -> None:
        for d in self.coordinator.data or []:
            if d.deviceId == self.device.deviceId:
                self.device = d
                break
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

    @property
    def is_on(self) -> bool | None:
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.device)
        return None
