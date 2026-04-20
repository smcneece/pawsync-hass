"""Sensor platform for Pawsync devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import pawsync
from .const import CONF_UNIT_SYSTEM, DOMAIN, PAWSYNC_COORDINATOR, UNIT_IMPERIAL

_LOGGER = logging.getLogger(__name__)


def _secs_to_time(secs: int | None) -> str | None:
    """Convert seconds-since-midnight to 'HH:MM' string."""
    if secs is None:
        return None
    h = (secs // 3600) % 24
    m = (secs % 3600) // 60
    return f"{h:02d}:{m:02d}"


@dataclass(frozen=True)
class PawsyncSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[pawsync.Device], Any] | None = None


SENSOR_TYPES: tuple[PawsyncSensorEntityDescription, ...] = (
    PawsyncSensorEntityDescription(
        key="primary",
        name=None,  # uses device name — shows connection status, carries all raw attributes
        value_fn=lambda d: d.deviceProp.get("connectionStatus"),
    ),
    PawsyncSensorEntityDescription(
        key="content_in_pot",
        name="Food in bowl",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bowl-mix",
        value_fn=lambda d: d.deviceProp.get("contentInPot"),
    ),
    PawsyncSensorEntityDescription(
        key="bucket_surplus",
        name="Hopper remaining",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:silo",
        value_fn=lambda d: (d.deviceProp.get("petFood") or {}).get("bucketSurplus"),
    ),
    PawsyncSensorEntityDescription(
        key="last_feeding_amount",
        name="Last feeding amount",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
        value_fn=lambda d: (d.deviceProp.get("petFood") or {}).get("lastFeedingAmount"),
    ),
    PawsyncSensorEntityDescription(
        key="content_remain_time",
        name="Food supply remaining",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
        value_fn=lambda d: (d.deviceProp.get("petFood") or {}).get("contentRemainTime"),
    ),
    PawsyncSensorEntityDescription(
        key="battery_percent",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.deviceProp.get("batteryPercent"),
    ),
    PawsyncSensorEntityDescription(
        key="wifi_rssi",
        name="WiFi signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.deviceProp.get("wifiRssi"),
    ),
    PawsyncSensorEntityDescription(
        key="alert_count",
        name="Alerts",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
        value_fn=lambda d: d.deviceProp.get("alertCount"),
    ),
    PawsyncSensorEntityDescription(
        key="main_fw_version",
        name="Firmware version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        value_fn=lambda d: next(
            (fw["version"] for fw in d.deviceProp.get("firmwareInfos", []) if fw.get("isMainFw")),
            None,
        ),
    ),
    PawsyncSensorEntityDescription(
        key="mcu_fw_version",
        name="MCU firmware version",
        icon="mdi:cpu-64-bit",
        entity_registry_enabled_default=False,
        value_fn=lambda d: next(
            (fw["version"] for fw in d.deviceProp.get("firmwareInfos", []) if fw.get("pluginName") == "mcuFw"),
            None,
        ),
    ),
    # Schedule / next meal
    PawsyncSensorEntityDescription(
        key="next_meal_time",
        name="Next meal time",
        icon="mdi:clock-outline",
        value_fn=lambda d: _secs_to_time((d.deviceProp.get("scheduleInfo") or {}).get("nextTime")),
    ),
    PawsyncSensorEntityDescription(
        key="next_meal_amount",
        name="Next meal amount",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale",
        value_fn=lambda d: (d.deviceProp.get("scheduleInfo") or {}).get("nextMount"),
    ),
    PawsyncSensorEntityDescription(
        key="daily_total",
        name="Daily food total",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sigma",
        value_fn=lambda d: (d.deviceProp.get("scheduleInfo") or {}).get("totalMealG"),
    ),
    # Network / misc
    PawsyncSensorEntityDescription(
        key="wifi_ssid",
        name="WiFi network",
        icon="mdi:wifi",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.deviceProp.get("wifiName"),
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
            PawsyncDeviceSensor(coordinator, d, desc)
            for d in coordinator.data
            for desc in SENSOR_TYPES
            if f"{d.deviceId}_{desc.key}" not in known_ids
        ]
        if new_entities:
            known_ids.update(f"{e.device.deviceId}_{e.entity_description.key}" for e in new_entities)
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


class PawsyncDeviceSensor(CoordinatorEntity, SensorEntity):

    entity_description: PawsyncSensorEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncSensorEntityDescription):
        super().__init__(coordinator)
        self.device = device
        self.entity_description = description
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"

        # Explicitly set unit so HA doesn't have to read it from entity_description
        if (description.native_unit_of_measurement == UnitOfMass.GRAMS
                and coordinator.config_entry.options.get(CONF_UNIT_SYSTEM, UNIT_IMPERIAL) == UNIT_IMPERIAL):
            self._attr_native_unit_of_measurement = UnitOfMass.OUNCES
        else:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

        if description.name is None:
            self._attr_name = device.deviceName
            self._attr_entity_picture = device.deviceImg
            self._attr_extra_state_attributes = self._build_full_attributes(device)
        else:
            self._attr_name = f"{device.deviceName} {description.name}"
            self._attr_extra_state_attributes = {"device_id": device.deviceId}

    @staticmethod
    def _build_full_attributes(device: pawsync.Device) -> dict[str, Any]:
        return {
            "device_id": device.deviceId,
            "device_name": device.deviceName,
            "device_model": device.deviceModel,
            "device_image": device.deviceImg,
            "connection_type": device.connectionType,
            "secondary_category": device.secondaryCategory,
            "config_model": device.configModel,
            "biz_id": device.bizId,
            "pet_id": device.petId,
            "device_prop": device.deviceProp,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        for d in self.coordinator.data or []:
            if d.deviceId == self.device.deviceId:
                self.device = d
                if self.entity_description.name is None:
                    self._attr_extra_state_attributes = self._build_full_attributes(d)
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
    def native_value(self) -> Any:
        if not self.entity_description.value_fn:
            return None
        val = self.entity_description.value_fn(self.device)
        if val is None:
            return None
        if self._attr_native_unit_of_measurement == UnitOfMass.OUNCES:
            return round(val * 0.035274, 2)
        return val
