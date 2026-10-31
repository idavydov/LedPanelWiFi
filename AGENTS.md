# Repository Guidelines

## Project Structure & Module Organization

- `firmware/LedPanelWiFi_v1.14/` contains Arduino C++ firmware. Sketch tabs separate networking, settings, weather, effects, and games; `a_def_hard.h` and `a_def_soft.h` define configuration.
- `web/src/app/` contains the Angular UI, organized into components, services, directives, and models. Templates and SCSS sit beside components.
- `firmware/LedPanelWiFi_v1.14/data/web/` contains compressed browser assets served from LittleFS.
- `libraries/` contains bundled dependencies, including ZIP archives requiring setup. `tests/` contains host security regressions. Hardware references and media live in `schemes/`, `pcb/`, `stl/`, `pics/`, `sounds/`, and `addons/`.

## Build, Test, and Development Commands

For generic builds, configure local device headers using the templates in `public.zip`. The S2 Mini profile uses browser setup instead; see `FLASHING_S2_MINI.md`.

- `pio run -e esp32` or `pio run -e esp8266`: build firmware for the selected PlatformIO environment.
- `pio run -e esp32 -t buildfs`: build the LittleFS image from the configured data directory.
- From `web/`, run `npm ci --legacy-peer-deps`, then `npm run build`: install locked dependencies and produce `dist/browser/`.
- From `web/`, run `npm start`: launch Angular development mode. Authenticated device WebSockets require the device's own origin; development hosting alone does not verify integration.
- `python3 -m unittest discover -s tests -v`: run host regressions; Python 3 and `g++` are required.

Follow `web/!!!readme!!!` when compressing and copying generated assets into firmware data.

## Coding Style & Naming Conventions

Match surrounding code; generally use two-space indentation in sketch functions and TypeScript. Preserve established firmware identifiers and uppercase configuration macros. Angular files use kebab-case names such as `tab-network-ssid.component.ts`, with PascalCase classes. No formatter or lint script is configured; avoid unrelated reformatting.

## Testing Guidelines

Use Python `unittest` files named `test_*.py`. Add meaningful regressions for security or behavioral changes. No coverage threshold is configured. Build affected firmware targets and the UI as appropriate; report untested hardware behavior explicitly.

## Commit & Pull Request Guidelines

History uses descriptive English and Russian commit subjects without a required prefix. Keep commits focused. PRs should explain behavior changes, reference relevant issues, report validation and board/core versions, and include screenshots for UI changes.

## Security & Agent Instructions

Keep `a_def_pass.h` and credentials uncommitted. Preserve mandatory administrator authentication and OTA password protection. When interacting with Cloudflare, use the `cf` CLI unless the project has a Wrangler configuration file.

Do not monitor provisioning sessions, inspect authenticated device pages, or download settings backups after credentials are entered. Never request or read the device's Wi-Fi password.
