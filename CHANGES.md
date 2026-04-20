# Pawsync HA Integration — Changes

## v0.2.0 (0.1.1 — 2026-04-19)

### Bug Fixes
- Sensor value was frozen at startup value and never updated
- Wrong password silently created a broken config entry with no error shown
- Crash when `contentInPot` key missing from API response
- Feed errors from the API were silently ignored
- Auth token was printed to HA logs on every feed request
- Duplicate account setup re-showed the form with no error message
- Entry unload left stale references in internal device/session registry
- **Phone app getting logged out after HA restarts** — fixed by using a stable terminal ID derived from the account email instead of a random one generated at startup *(credit: PR #2 by @tomsalden)*

### New Features
- **Options flow** — edit email, password, units, meal size, and polling interval via the gear icon without removing the integration
- **Feed Now button entity** — pressable from dashboards, automations, and scripts; reads meal size from options at press time
- **14 additional sensors** — food in bowl, hopper remaining, last feeding amount, food supply remaining (days), next meal time, next meal amount, daily food total, battery %, alert count, WiFi signal, WiFi network, connection status, main firmware version, MCU firmware version
- **5 binary sensors** — power adapter, intelligent feeding, slow feed, accurate feeding, sleep mode
- **US/metric unit toggle** — options flow lets you choose oz or grams; all weight sensors convert automatically; defaults to US (oz)
- Proper HA units and device classes on all sensors (grams/oz, %, dBm, days)
- New feeders added to the account appear automatically without restarting HA
- Coordinator now surfaces errors to the HA UI instead of silently returning empty data
- Sensors without a unit (alerts, battery, next meal time, firmware versions, WiFi) showing as Unavailable — fixed by explicitly setting `native_unit_of_measurement` on all sensor entities

### Credits
- Original: [@jasonmeisel](https://github.com/jasonmeisel)
- Session fix (PR #2): [@tomsalden](https://github.com/tomsalden)
- Sensor ideas (PR #1): [@asssaf](https://github.com/asssaf)
