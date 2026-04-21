"""Constants for the Pawsync integration."""

from homeassistant.const import Platform

DOMAIN = "pawsync"
PAWSYNC_COORDINATOR = "pawsync_coordinator"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH, Platform.TIME, Platform.NUMBER]

CONF_MEAL_SIZE = "meal_size"
CONF_UNIT_SYSTEM = "unit_system"
UNIT_IMPERIAL = "imperial"
UNIT_METRIC = "metric"

DEFAULT_MEAL_SIZE = 11
DEFAULT_UPDATE_INTERVAL = 15  # minutes

TOKEN_INVALID_CODE = -11008800  # Pawsync API code when auth token has expired
