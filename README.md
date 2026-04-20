# Pawsync — Home Assistant Integration

Monitor and control your Pawsync smart pet feeder from Home Assistant. View food levels, battery, schedule info, and trigger manual feedings — all from your dashboard or automations.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/smcneece/pawsync-hass)](https://github.com/smcneece/pawsync-hass/releases)
[![GitHub](https://img.shields.io/github/license/smcneece/pawsync-hass)](LICENSE)

> This integration is not affiliated with or endorsed by Pawsync.

---

## Installation

### Via HACS (Recommended)

**Don't have HACS?** [Install it first](https://www.hacs.xyz/docs/use/) — it handles updates automatically.

1. Click the button below to add this repository to HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=smcneece&repository=pawsync-hass&category=integration)

2. Click **Add**, then **Download** the integration.
3. Restart Home Assistant when prompted.
4. Click the button below to start setup:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pawsync)

### Manual Installation

1. Copy the `custom_components/pawsync` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for **Pawsync**.

---

## Configuration

Enter your Pawsync account email and password. Credentials are validated against the Pawsync API before the entry is created.

### Options (gear icon on the integration)

| Setting | Default | Description |
|---------|---------|-------------|
| Units | US (oz) | Display weight sensors in ounces or grams |
| Default meal size | 12 | Portions dispensed by the Feed Now button and feed service |
| Polling interval | 15 min | How often HA fetches updated device state |
| Email / Password | — | Update credentials without removing the integration |

---

## Entities

### Sensors

| Entity | Unit | Notes |
|--------|------|-------|
| Smart Pet Feeder | — | Connection status; carries all raw device attributes |
| Food in bowl | oz / g | Current food level in the bowl |
| Hopper remaining | oz / g | Food remaining in the reservoir |
| Last feeding amount | oz / g | Amount dispensed at the last feeding |
| Food supply remaining | days | Estimated days until hopper is empty |
| Next meal time | HH:MM | Time of next scheduled feeding |
| Next meal amount | oz / g | Amount to be dispensed at next meal |
| Daily food total | oz / g | Total food scheduled per day |
| Battery | % | Battery level (when running on battery) |
| Alerts | count | Active alert count |
| WiFi signal | dBm | Signal strength *(disabled by default)* |
| WiFi network | — | Connected SSID *(disabled by default)* |
| Firmware version | — | Main firmware version *(disabled by default)* |
| MCU firmware version | — | MCU firmware version *(disabled by default)* |

### Binary Sensors

| Entity | Notes |
|--------|-------|
| Power adapter | On = plugged in |
| Sleep mode | On = quiet hours active |
| Intelligent feeding | On = auto-schedule enabled |
| Slow feed | On = slow dispensing mode active |
| Accurate feeding | On = accurate feeding mode active |

### Controls

| Entity | Notes |
|--------|-------|
| Feed Now (button) | Dispenses one meal at the configured meal size |

---

## Services

### `pawsync.feed`

Trigger a manual feeding from an automation or script.

```yaml
action: pawsync.feed
data:
  entity_id: sensor.smart_pet_feeder
  amount: 12  # optional — overrides the default meal size
```

### Alexa / Voice Control

Create a script in Home Assistant and expose it to Alexa:

```yaml
# In your scripts.yaml
feed_the_cat:
  alias: "Feed the Cat"
  sequence:
    - action: button.press
      target:
        entity_id: button.smart_pet_feeder_feed_now
```

Then say: **"Alexa, run Feed the Cat"** — or set up an Alexa Routine with a custom trigger phrase.

---

## Credits

- **Original integration**: [@jasonmeisel](https://github.com/jasonmeisel)
- **v0.2.0 enhancements**: [@smcneece](https://github.com/smcneece) — bug fixes, expanded sensors, options flow, unit conversion, HACS support
- **Session stability fix**: [@tomsalden](https://github.com/tomsalden) (PR #2)
- **Sensor expansion ideas**: [@asssaf](https://github.com/asssaf) (PR #1)

See [CHANGES.md](CHANGES.md) for full changelog.
