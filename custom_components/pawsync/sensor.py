"""Sensor platform for Pawsync devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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


# ── Device property sensors ────────────────────────────────────────────────────

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
        key="bowl_weight",
        name="Food in bowl",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bowl-mix",
        value_fn=lambda d: d.deviceProp.get("bowlWeight"),
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
    PawsyncSensorEntityDescription(
        key="wifi_ssid",
        name="WiFi network",
        icon="mdi:wifi",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.deviceProp.get("wifiName"),
    ),
    PawsyncSensorEntityDescription(
        key="desiccant_remaining",
        name="Desiccant remaining",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
        value_fn=lambda d: d.deviceProp.get("desiccantRemainTime"),
    ),
)


# ── Pet log sensors ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PawsyncLogSensorEntityDescription(SensorEntityDescription):
    log_fn: Callable[[list], Any] | None = None


LOG_SENSOR_TYPES: tuple[PawsyncLogSensorEntityDescription, ...] = (
    PawsyncLogSensorEntityDescription(
        key="last_dispensed_time",
        name="Last dispensed time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check",
        log_fn=lambda logs: next(
            (datetime.fromtimestamp(e["timestamp"], tz=timezone.utc)
             for e in logs if e["logType"] in ("planFeeding", "manualFeeding")),
            None,
        ),
    ),
    PawsyncLogSensorEntityDescription(
        key="last_dispensed_amount",
        name="Last dispensed amount",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker-outline",
        log_fn=lambda logs: next(
            (e["value"] for e in logs
             if e["logType"] in ("planFeeding", "manualFeeding") and e.get("value") is not None),
            None,
        ),
    ),
    PawsyncLogSensorEntityDescription(
        key="last_eaten_time",
        name="Last eaten time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:cat",
        log_fn=lambda logs: next(
            (datetime.fromtimestamp(e["timestamp"], tz=timezone.utc)
             for e in logs if e["logType"] == "takeFood"),
            None,
        ),
    ),
    PawsyncLogSensorEntityDescription(
        key="last_eaten_amount",
        name="Last eaten amount",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:food-variant",
        log_fn=lambda logs: next(
            (e["value"] for e in logs
             if e["logType"] == "takeFood" and e.get("value") is not None),
            None,
        ),
    ),
    PawsyncLogSensorEntityDescription(
        key="last_eating_duration",
        name="Last eating duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer",
        log_fn=lambda logs: next(
            (e["durationInS"] for e in logs
             if e["logType"] == "takeFood" and e.get("durationInS", -1) > 0),
            None,
        ),
    ),
)


# ── Pet profile sensors ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PawsyncPetSensorEntityDescription(SensorEntityDescription):
    pet_fn: Callable[[dict], Any] | None = None


PET_SENSOR_TYPES: tuple[PawsyncPetSensorEntityDescription, ...] = (
    PawsyncPetSensorEntityDescription(
        key="pet_weight",
        name="Weight",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:scale-bathroom",
        pet_fn=lambda p: p.get("weightInG"),
    ),
    PawsyncPetSensorEntityDescription(
        key="today_food_intake",
        name="Food intake today",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bowl",
        pet_fn=lambda p: p.get("todayFoodIntakeInG"),
    ),
    PawsyncPetSensorEntityDescription(
        key="today_food_target",
        name="Daily food target",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:target",
        pet_fn=lambda p: p.get("targetFoodIntakeInG"),
    ),
    PawsyncPetSensorEntityDescription(
        key="today_feeding_times",
        name="Feedings today",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        pet_fn=lambda p: p.get("todayFoodIntakeTimes"),
    ),
)


# ── Platform setup ─────────────────────────────────────────────────────────────

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
        devices = coordinator.data["devices"]
        pet_logs = coordinator.data["pet_logs"]
        pets = coordinator.data["pets"]

        new_entities: list = []

        # Device property sensors
        for d in devices:
            for desc in SENSOR_TYPES:
                key = f"{d.deviceId}_{desc.key}"
                if key not in known_ids:
                    new_entities.append(PawsyncDeviceSensor(coordinator, d, desc))
                    known_ids.add(key)

        # Pet log sensors
        for d in devices:
            logs = pet_logs.get(d.deviceId, [])
            for desc in LOG_SENSOR_TYPES:
                key = f"{d.deviceId}_{desc.key}"
                if key not in known_ids:
                    new_entities.append(PawsyncLogSensor(coordinator, d, desc, logs))
                    known_ids.add(key)

        # Pet profile sensors
        for d in devices:
            pet = pets.get(d.petId)
            if pet:
                for desc in PET_SENSOR_TYPES:
                    key = f"{d.deviceId}_{desc.key}"
                    if key not in known_ids:
                        new_entities.append(PawsyncPetSensor(coordinator, d, desc, pet))
                        known_ids.add(key)

        if new_entities:
            async_add_entities(new_entities)

    coordinator.async_add_listener(_check_for_new)
    _check_for_new()


# ── Entity classes ─────────────────────────────────────────────────────────────

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
        for d in (self.coordinator.data or {}).get("devices", []):
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


class PawsyncLogSensor(CoordinatorEntity, SensorEntity):

    entity_description: PawsyncLogSensorEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncLogSensorEntityDescription, logs: list):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._logs = logs
        self.entity_description = description
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"
        self._attr_name = f"{device.deviceName} {description.name}"
        self._attr_extra_state_attributes = {"device_id": device.deviceId}

        use_imperial = coordinator.config_entry.options.get(CONF_UNIT_SYSTEM, UNIT_IMPERIAL) == UNIT_IMPERIAL
        if description.native_unit_of_measurement == UnitOfMass.GRAMS and use_imperial:
            self._attr_native_unit_of_measurement = UnitOfMass.OUNCES
        else:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @callback
    def _handle_coordinator_update(self) -> None:
        self._logs = (self.coordinator.data or {}).get("pet_logs", {}).get(self._device_id, [])
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        devices = (self.coordinator.data or {}).get("devices", [])
        d = next((d for d in devices if d.deviceId == self._device_id), None)
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
    def native_value(self) -> Any:
        if not self.entity_description.log_fn:
            return None
        val = self.entity_description.log_fn(self._logs)
        if val is None:
            return None
        if self._attr_native_unit_of_measurement == UnitOfMass.OUNCES:
            return round(val * 0.035274, 2)
        return val


class PawsyncPetSensor(CoordinatorEntity, SensorEntity):

    entity_description: PawsyncPetSensorEntityDescription

    def __init__(self, coordinator, device: pawsync.Device, description: PawsyncPetSensorEntityDescription, pet: dict):
        super().__init__(coordinator)
        self._device_id = device.deviceId
        self._pet_id = device.petId
        self._pet = pet
        self.entity_description = description
        self._attr_unique_id = f"pawsync_{device.deviceId}_{description.key}"
        pet_name = pet.get("petName") or device.deviceName
        self._attr_name = f"{pet_name} {description.name}"
        self._attr_entity_picture = pet.get("petAvatarIcon")
        self._attr_extra_state_attributes = {"device_id": device.deviceId, "pet_name": pet_name}

        use_imperial = coordinator.config_entry.options.get(CONF_UNIT_SYSTEM, UNIT_IMPERIAL) == UNIT_IMPERIAL
        if description.native_unit_of_measurement == UnitOfMass.GRAMS and use_imperial:
            if description.key == "pet_weight":
                self._attr_native_unit_of_measurement = UnitOfMass.POUNDS
            else:
                self._attr_native_unit_of_measurement = UnitOfMass.OUNCES
        elif description.native_unit_of_measurement == UnitOfMass.GRAMS and not use_imperial:
            if description.key == "pet_weight":
                self._attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
            else:
                self._attr_native_unit_of_measurement = UnitOfMass.GRAMS
        else:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @callback
    def _handle_coordinator_update(self) -> None:
        self._pet = (self.coordinator.data or {}).get("pets", {}).get(self._pet_id, self._pet)
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        devices = (self.coordinator.data or {}).get("devices", [])
        d = next((d for d in devices if d.deviceId == self._device_id), None)
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
    def native_value(self) -> Any:
        if not self.entity_description.pet_fn:
            return None
        val = self.entity_description.pet_fn(self._pet)
        if val is None:
            return None
        if self._attr_native_unit_of_measurement == UnitOfMass.OUNCES:
            return round(val * 0.035274, 2)
        if self._attr_native_unit_of_measurement == UnitOfMass.POUNDS:
            return round(val * 0.00220462, 2)
        if self._attr_native_unit_of_measurement == UnitOfMass.KILOGRAMS:
            return round(val / 1000, 2)
        return val
