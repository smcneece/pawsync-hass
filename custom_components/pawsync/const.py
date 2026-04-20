"""Constants for the Pawsync integration."""

from homeassistant.const import Platform

DOMAIN = "pawsync"
PAWSYNC_COORDINATOR = "pawsync_coordinator"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CONF_MEAL_SIZE = "meal_size"
CONF_UNIT_SYSTEM = "unit_system"
UNIT_IMPERIAL = "imperial"
UNIT_METRIC = "metric"

DEFAULT_MEAL_SIZE = 12
DEFAULT_UPDATE_INTERVAL = 15  # minutes
