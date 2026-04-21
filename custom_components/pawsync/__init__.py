"""
Pawsync Home Assistant integration.

Entry points:
  async_setup        — registers the legacy YAML-based pawsync.feed service
  async_setup_entry  — sets up the DataUpdateCoordinator and forwards to platforms
  async_unload_entry — tears down coordinator and cleans up device registry

Data flow each poll (async_update):
  1. getDeviceList        — base device list with cached deviceProp
  2. getStatus (bypassV2) — live data merged into deviceProp (bowl weight, desiccant, etc.)
  3. getPetLogList        — last 24h feeding activity per device
  4. getPetList           — pet profiles (weight, intake, avatar)
  5. getFirmwareUpdateInfo — firmware update availability

Coordinator data shape:
  {
    "devices":          list[Device],
    "pet_logs":         {deviceId: list[log_entry]},
    "pets":             {petId: dict},
    "firmware_updates": {deviceId: list[firmware_info]},
  }
"""

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

# Legacy YAML config schema — kept for backwards compatibility.
# New installs use the config flow (UI).
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

# Module-level dicts that bridge the global pawsync.feed service to the
# per-entry coordinator. The service is registered once in async_setup but
# needs to reach devices that load later via config entries.
all_devices: dict[str, pawsync.Device] = {}
sessions: dict[str, aiohttp.ClientSession] = {}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # If YAML config exists, kick off a config flow import so the entry
    # gets created via the normal config entry path.
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=config[DOMAIN],
            )
        )

    async def handle_feed(call: ServiceCall):
        """Service handler for pawsync.feed.

        Resolves entity_id → device_id via entity state attributes,
        then looks up the device and session from the module-level dicts.
        """
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
        """Fetch all data from the Pawsync API.

        If getDeviceList returns nothing, the token has likely expired —
        re-authenticate and try once more before raising UpdateFailed.
        """
        devices = await pawsync.getDeviceList(session, logger)
        if not devices:
            try:
                await pawsync.login(session, username, password)
            except pawsync.PawsyncAuthError as err:
                raise UpdateFailed(f"Re-authentication failed: {err}") from err
            devices = await pawsync.getDeviceList(session, logger)
            if not devices:
                raise UpdateFailed("Could not retrieve device list after re-auth")

        # Keep the module-level dicts in sync so the feed service can reach devices.
        for d in devices:
            sessions[d.deviceId] = session
            all_devices[d.deviceId] = d

        # Merge live device status into deviceProp. deviceList4Pet returns
        # cached data for bowl weight and desiccant; getPetDeviceStatus has
        # the real-time values from the physical device.
        for d in devices:
            status = await d.getStatus(session, logger)
            if status:
                d.deviceProp.update(status)

        pet_logs = {}
        for d in devices:
            pet_logs[d.deviceId] = await pawsync.getPetLogList(session, d.deviceId, logger)

        pets_list = await pawsync.getPetList(session, logger)
        pets = {p["petId"]: p for p in pets_list}

        firmware_updates = await pawsync.getFirmwareUpdateInfo(
            session, [d.deviceId for d in devices], logger
        )

        return {"devices": devices, "pet_logs": pet_logs, "pets": pets, "firmware_updates": firmware_updates}

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
            for device in coordinator.data.get("devices", []):
                all_devices.pop(device.deviceId, None)
                sessions.pop(device.deviceId, None)
    return unload_ok
