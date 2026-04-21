# Pawsync HA Integration — Changes

## v0.3.1 (0.3.1 — 2026-04-20)

### Bug Fixes
- **Auth token expiry** — button presses (Extra Meal, etc.) and switch commands silently failed when the Pawsync API token expired mid-session. The integration now automatically re-authenticates and retries, so commands work without requiring an HA restart. This was the root cause of Alexa routines appearing to fire (last triggered timestamp updated) but no food being dispensed.

### Documentation
- Alexa voice control instructions updated — expose the Extra Meal button directly to Alexa instead of going through a script; it appears under Smart Home scenes in the Alexa app
- Added tip to name feeders and pets in the Pawsync app before adding the integration for cleaner entity names

---

## v0.3.0

### Bug Fixes
- Sensor value was frozen at startup value and never updated
- Wrong password silently created a broken config entry with no error shown
- Crash when `contentInPot` key missing from API response
- Feed errors from the API were silently ignored
- Auth token was printed to HA logs on every feed request
- Duplicate account setup re-showed the form with no error message
- Entry unload left stale references in internal device/session registry
- **Phone app getting logged out after HA restarts** — fixed by using a stable terminal ID derived from the account email instead of a random one generated at startup *(credit: PR #2 by @tomsalden)*
- Switches (Smart Feeding, Slow Feeding, Precision Mode, Sleep Mode) reverting to previous state immediately after being toggled — fixed with optimistic state update
- Sleep Mode toggle silently rejected by device — fixed by including `startClkSec`/`endClkSec` in the payload, matching what the app sends
- "Food in bowl" sensor showing stale server-cached value instead of live scale reading
- Desiccant remaining sensor showing Unknown — now reads from `getPetDeviceStatus` which exposes the value
- `getPetList` failing with internal server error — wrong API service path (`petDeviceManaged` → `petManaged`)

### New Features
- **Options flow** — edit email, password, units, meal size, and polling interval via the gear icon without removing the integration
- **4 switches** — Smart Feeding, Slow Feeding, Precision Mode, Sleep Mode; all controllable from dashboards and automations
- **5 buttons** — Extra Meal, Zero Scale, Meal Call, Reset Desiccant, Refresh
- **Live bowl weight** — "Food in bowl" now reads the real-time scale via `getPetDeviceStatus` instead of stale server data
- **Pet log sensors** — Last dispensed time/amount, last eaten time/amount, last eating duration (from last 24h activity log)
- **Pet profile sensors** — Weight, food intake today, daily food target, feedings today; named after the pet (e.g. "Finn Weight") with the pet's avatar photo as the entity icon
- **Desiccant remaining** sensor (days) and **Reset Desiccant** button
- **Sleep mode schedule** — two time entities (Sleep Mode Start, Sleep Mode End) with time pickers; automatable for different weekday/weekend schedules
- **Hopper level** — slider control (1000–3600ml) to record food level after refilling; updates "Food supply remaining" days estimate automatically
- **Firmware update binary sensor** — turns on when a firmware update is available; attributes show current/latest version and release notes per firmware component
- **Food bowl binary sensor** — OK when placed, Problem when removed; works naturally with HA automations
- **Refresh button** — forces an immediate coordinator refresh without reloading the integration
- **US/metric unit toggle** — options flow lets you choose oz or grams; all weight sensors convert automatically; defaults to US (oz)
- Extra meal size slider (11g–110g in 11g steps) matching the app's 0.4–3.9 oz portion range
- Proper HA units and device classes on all sensors
- New feeders added to the account appear automatically without restarting HA
- Coordinator now surfaces errors to the HA UI instead of silently returning empty data

### Planned / To-Do
- **Feeding schedule** — `getFeedingPlanList` / `getFeedingPlanDetail` already sniffed; surface feeding plan times as sensors or calendar events

### Credits
- Original: [@jasonmeisel](https://github.com/jasonmeisel)
- Session fix (PR #2): [@tomsalden](https://github.com/tomsalden)
- Sensor ideas (PR #1): [@asssaf](https://github.com/asssaf)
