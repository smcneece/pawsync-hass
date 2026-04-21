# Pawsync — Home Assistant Integration

Monitor and control your Pawsync smart pet feeder from Home Assistant. View live food levels, pet stats, feeding history, and control your feeder — all from your dashboard or automations.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HACS Action](https://github.com/smcneece/pawsync-hass/actions/workflows/validate.yaml/badge.svg)](https://github.com/smcneece/pawsync-hass/actions/workflows/validate.yaml)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/smcneece/pawsync-hass)](https://github.com/smcneece/pawsync-hass/releases)
[![GitHub](https://img.shields.io/github/license/smcneece/pawsync-hass)](LICENSE)

> This integration is not affiliated with or endorsed by Pawsync.

> **Tip:** Entity and device names come directly from the Pawsync app. Before installing, name your feeder(s) and pet(s) in the app the way you want them to appear in Home Assistant — for example, naming your feeder "Finn's Feeder" and your pet "Finn" will produce clean entity names like `sensor.finn_s_feeder_food_in_bowl` and `sensor.finn_weight`.

---

## Installation

### Via HACS (Recommended)

**Don't have HACS?** [Install it first](https://www.hacs.xyz/docs/use/) — it handles updates automatically.

1. Click the button below to add this repository to HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=smcneece&repository=pawsync-hass&category=integration)

2. Click **Add**, then **Download** button in bottom right corner the integration.
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
| Extra meal size | 11g (1 portion) | Amount dispensed by the Extra Meal button; 11g = 1 portion ≈ 0.4 oz |
| Polling interval | 15 min | How often HA fetches updated device state |
| Email / Password | — | Update credentials without removing the integration |

---

## Entities

### Feeder Sensors

| Entity | Unit | Notes |
|--------|------|-------|
| Smart Pet Feeder | — | Connection status; carries all raw device attributes |
| Food in bowl | oz / g | Live bowl scale reading |
| Hopper remaining | oz / g | Food remaining in the reservoir |
| Last feeding amount | oz / g | Amount dispensed at the last feeding |
| Desiccant remaining | days | Days until desiccant pack needs replacing |
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

### Pet Log Sensors

Updated each poll with the most recent activity from the last 24 hours.

| Entity | Unit | Notes |
|--------|------|-------|
| Last dispensed time | timestamp | When food was last dispensed |
| Last dispensed amount | oz / g | How much was dispensed |
| Last eaten time | timestamp | When the pet last ate |
| Last eaten amount | oz / g | How much the pet ate |
| Last eating duration | seconds | How long the eating session lasted |

### Pet Profile Sensors

Named after the pet assigned to the feeder in the app (e.g. "Finn Weight").

| Entity | Unit | Notes |
|--------|------|-------|
| Weight | lb / kg | Pet's weight as recorded in the app |
| Food intake today | oz / g | Amount eaten so far today |
| Daily food target | oz / g | Daily food target set in the app |
| Feedings today | count | Number of feeding sessions today |

### Binary Sensors

| Entity | Notes |
|--------|-------|
| Power adapter | On = plugged in |
| Food bowl | OK = bowl is placed; Problem = bowl is missing (use for automations) |
| Firmware update | On = update available; attributes show version and release notes |

### Switches

| Entity | Notes |
|--------|-------|
| Smart Feeding | Enables automatic schedule-based feeding |
| Slow Feeding | Dispenses food slowly to prevent gulping |
| Precision Mode | Accurate portion measurement mode |
| Sleep Mode | Quiet hours — suppresses sounds during set times |

### Buttons

| Entity | Notes |
|--------|-------|
| Extra Meal | Dispenses one meal at the configured meal size |
| Zero Scale | Tares the bowl scale to zero |
| Meal Call | Plays the meal call sound |
| Reset Desiccant | Resets the desiccant countdown to 30 days |
| Refresh | Forces an immediate data refresh without waiting for the next poll |

### Time

| Entity | Notes |
|--------|-------|
| Sleep Mode 1 Start | Time quiet hours begin |
| Sleep Mode 2 End | Time quiet hours end |

### Number

| Entity | Notes |
|--------|-------|
| Hopper level | Set food level after refilling (1000–3600ml); updates food supply remaining days automatically |

---

## Automations

### Different sleep schedule for weekdays vs weekends

The app only supports a single sleep schedule, but HA automations can change it automatically based on the day of the week.

```yaml
automation:
  - alias: "Feeder sleep schedule - weekdays"
    trigger:
      - platform: time
        at: "00:01:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - action: time.set_value
        target:
          entity_id: time.smart_pet_feeder_sleep_mode_1_start
        data:
          time: "22:00:00"
      - action: time.set_value
        target:
          entity_id: time.smart_pet_feeder_sleep_mode_2_end
        data:
          time: "07:00:00"

  - alias: "Feeder sleep schedule - weekends"
    trigger:
      - platform: time
        at: "00:01:00"
    condition:
      - condition: time
        weekday: [sat, sun]
    action:
      - action: time.set_value
        target:
          entity_id: time.smart_pet_feeder_sleep_mode_1_start
        data:
          time: "23:00:00"
      - action: time.set_value
        target:
          entity_id: time.smart_pet_feeder_sleep_mode_2_end
        data:
          time: "09:00:00"
```

### Firmware update notification

```yaml
automation:
  - alias: "Feeder firmware update available"
    trigger:
      - platform: state
        entity_id: binary_sensor.smart_pet_feeder_firmware_update
        to: "on"
    action:
      - action: notify.mobile_app_your_phone
        data:
          message: "A firmware update is available for your Pawsync feeder!"
```

### Bowl missing alert

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.smart_pet_feeder_food_bowl
    to: "on"
action:
  - action: notify.mobile_app_your_phone
    data:
      message: "Finn's food bowl has been removed!"
```

---

## Services

### `pawsync.feed`

Trigger a manual feeding from an automation or script.

```yaml
action: pawsync.feed
data:
  entity_id: sensor.smart_pet_feeder
  amount: 11  # optional — grams to dispense (11g = 1 portion ≈ 0.4 oz)
```

### Alexa / Voice Control

**Step 1** — Expose the Extra Meal button to Alexa:

In Home Assistant, go to **Settings → Voice Assistants → Amazon Alexa** and expose the `Extra Meal` button for your feeder. Then open the Alexa app and run a device discovery (or say *"Alexa, discover devices"*).

**Step 2** — Create a Routine in the Alexa app:
- Trigger: *"When I say: Feed Finn"* (or whatever phrase you want)
- Action: **Smart Home → Control →** select your feeder's **Extra Meal** button (it appears under Scenes)

Then just say: **"Alexa, Feed Finn"**

---

## Credits

- **Original integration**: [@jasonmeisel](https://github.com/jasonmeisel)
- **Major enhancements**: [@smcneece](https://github.com/smcneece) — bug fixes, expanded sensors, switches, pet log & profile sensors, live bowl weight, options flow, unit conversion, HACS support
- **Session stability fix**: [@tomsalden](https://github.com/tomsalden) (PR #2)
- **Sensor expansion ideas**: [@asssaf](https://github.com/asssaf) (PR #1)

See [CHANGES.md](CHANGES.md) for full changelog.
