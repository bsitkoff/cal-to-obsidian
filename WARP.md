# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project overview
A macOS-only Python utility that reads calendar events via EventKit (through PyObjC) and writes a daily Markdown note into an Obsidian vault. Primary entrypoint is `cal_to_obsidian.py`. Automation is handled by a `launchd` user agent installed by `install_automation.sh`.

Supported OS: macOS (EventKit is required).

## Common commands
- First-time setup
  - Ensure Python 3 and pip are available, then:
    - `chmod +x setup.sh && ./setup.sh`
- Manual export (today)
  - `./cal_to_obsidian.py`
- Manual export for a specific date
  - Tomorrow: `./cal_to_obsidian.py --date tomorrow`
  - Relative: `./cal_to_obsidian.py --date +3`
  - Absolute (YYYY-MM-DD): `./cal_to_obsidian.py --date 2025-11-17`
  - Also accepts `MM/DD/YYYY`
- Discover available calendars (for filtering)
  - `./cal_to_obsidian.py --list-calendars`
- Install or refresh automation (runs several times per day)
  - `chmod +x install_automation.sh && ./install_automation.sh`
- Observe logs while automated
  - `tail -f logs/output.log`
  - Errors: `tail -f logs/error.log`
- Uninstall automation
  - `launchctl unload ~/Library/LaunchAgents/com.user.cal-to-obsidian.plist && rm ~/Library/LaunchAgents/com.user.cal-to-obsidian.plist`
- Reset calendar permissions if needed
  - `tccutil reset Calendar com.apple.Terminal`

Notes
- On first run you must execute `./cal_to_obsidian.py` interactively to grant Calendar access, before enabling automation.
- The output note path and name are controlled by `config.yaml`.

## Configuration
All runtime behavior is configured via `config.yaml` (created from `config.example.yaml` by `setup.sh`). Key fields:
- `obsidian_vault_path`: Destination directory for the generated note (supports `~`).
- `calendar_note_name`: Filename; supports `strftime` formatting for dated names (e.g., `%Y-%m-%d-Calendar.md`).
- `calendar_set`: Logical grouping label; EventKit cannot access Fantastical sets directly. Use `"all"` to include all calendars, then filter explicitly via `calendar_filter`.
- `calendar_filter`: Optional list of calendar titles to include; if empty, all calendars are considered.
- Display options: `show_calendar_name`, `show_location`, `show_notes`.
- `context_note`: Optional explanatory blockquote inserted at the top of the note to guide AI assistants.

## High-level architecture
- cal_to_obsidian.py (single-entry CLI)
  - Parses arguments (`--date`, `--list-calendars`).
  - Ensures `config.yaml` exists (bootstraps from example if missing).
  - Instantiates `CalendarExporter`:
    - Loads YAML config.
    - Validates calendar authorization via EventKit and exits if not authorized.
  - Core flow (for a target date):
    1) Resolve calendars
       - EventKit provides all calendars; Fantastical “sets” aren’t exposed. Optional `calendar_filter` narrows by title.
    2) Fetch events
       - Build a day-bounded predicate and query EventKit for the selected calendars.
    3) Render Markdown
       - Header with date and "Last updated" timestamp.
       - Optional `context_note` blockquote.
       - Sorted event list with time range, title, optional calendar name/location/notes.
    4) Write note
       - Resolve `obsidian_vault_path` and `calendar_note_name` (strftime-supported), ensure parent directories, write file.
- install_automation.sh
  - Verifies calendar access by invoking `--list-calendars` (fails fast if not granted).
  - Writes a user `launchd` plist at `~/Library/LaunchAgents/com.user.cal-to-obsidian.plist` that runs at 06:00, 09:00, 12:00, and 18:00, with stdout/stderr to `logs/`.
  - Loads the agent via `launchctl`.
- setup.sh
  - Verifies Python/pip, installs dependencies from `requirements.txt`, creates `config.yaml` if missing, and marks the CLI executable.

## Files of interest (non-exhaustive)
- `cal_to_obsidian.py`: CLI and core logic (EventKit integration, Markdown generation, file export).
- `config.yaml` / `config.example.yaml`: Runtime configuration.
- `install_automation.sh`: Launch agent installation and schedule.
- `setup.sh`: Dependency installation and initial config creation.
- `requirements.txt`: Minimal dependency pinning (PyObjC EventKit bridge, PyYAML).
- `logs/`: StandardOut/StandardError output for automated runs.

## Integration details and limitations
- macOS only: Requires EventKit via `pyobjc-framework-EventKit`.
- Fantastical calendar “sets” are not accessible through EventKit; use `--list-calendars` and `calendar_filter` to emulate set membership.
- The tool writes directly to the filesystem; it does not modify Obsidian metadata.

## Pulling important details forward from README
- First run must be manual for permission prompts.
- Automation cadence and management is via `launchctl` and a user LaunchAgent.
- Troubleshooting focuses on permissions and verifying that the LaunchAgent is loaded; logs are under `logs/`.
