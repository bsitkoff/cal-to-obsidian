#!/usr/bin/env python3
"""
Fantastical to Obsidian Calendar Exporter
Exports today's calendar events to a consistent Obsidian note.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import yaml

# Resolve the directory containing this script, regardless of current working directory
SCRIPT_DIR = Path(__file__).resolve().parent

try:
    from Foundation import NSDate, NSPredicate
    from EventKit import EKEventStore, EKEntityTypeEvent
except ImportError:
    print("Error: PyObjC not installed. Run: pip3 install pyobjc-framework-EventKit")
    sys.exit(1)


class CalendarExporter:
    def __init__(self, config_path="config.yaml"):
        """Initialize the calendar exporter with configuration."""
        # Ensure config_path is absolute; if relative, resolve relative to script dir
        cfg_path = Path(config_path)
        if not cfg_path.is_absolute():
            cfg_path = SCRIPT_DIR / cfg_path
        self.config = self.load_config(str(cfg_path))
        self.store = EKEventStore.alloc().init()
        self.request_calendar_access()

    def load_config(self, config_path):
        """Load configuration from YAML file."""
        if not os.path.exists(config_path):
            print(f"Error: Config file not found: {config_path}")
            print("Please copy config.example.yaml to config.yaml and edit it.")
            sys.exit(1)

        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def request_calendar_access(self):
        """Ensure calendar access is authorized; trigger the OS prompt if needed.

        On macOS, simply checking authorizationStatus does not trigger the TCC prompt.
        We must call requestAccessToEntityType:completion: once when status is NotDetermined.
        """
        from EventKit import (
            EKAuthorizationStatusAuthorized,
            EKAuthorizationStatusDenied,
            EKAuthorizationStatusRestricted,
            EKAuthorizationStatusNotDetermined,
            EKEventStore
        )
        from Foundation import NSRunLoop, NSDate

        def check_status():
            return EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)

        status = check_status()

        # Map status codes to readable strings
        status_map = {
            EKAuthorizationStatusNotDetermined: "not determined",
            EKAuthorizationStatusRestricted: "restricted",
            EKAuthorizationStatusDenied: "denied",
            EKAuthorizationStatusAuthorized: "authorized"
        }

        if status == EKAuthorizationStatusNotDetermined:
            # Trigger the permission dialog and synchronously wait for completion
            finished = {'done': False, 'granted': False}

            def _completion(granted, error):  # PyObjC bridges the block
                finished['granted'] = bool(granted)
                finished['done'] = True

            self.store.requestAccessToEntityType_completion_(EKEntityTypeEvent, _completion)
            # Pump the run loop until completion is called
            while not finished['done']:
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

            # Re-check resulting status
            status = check_status()

        status_str = status_map.get(status, "unknown")

        if status != EKAuthorizationStatusAuthorized:
            print(f"⚠️  Calendar access is {status_str}")
            if status == EKAuthorizationStatusDenied:
                print("Calendar access denied. Check System Settings → Privacy & Security → Calendars.")
            elif status == EKAuthorizationStatusRestricted:
                print("Calendar access restricted by system policy.")
            # Exit when not authorized - can't fetch calendars without permission
            sys.exit(1)

        return True

    def get_calendar_set_calendars(self, set_name):
        """Get all calendars in a specific calendar set."""
        calendars = []
        all_calendars = self.store.calendarsForEntityType_(EKEntityTypeEvent)

        # Fantastical calendar sets aren't directly accessible via EventKit
        # So we'll get all calendars and let user filter by name if needed
        # Or use all calendars if set_name is "all"

        if set_name.lower() == "all":
            return list(all_calendars)

        # For now, we'll include all calendars and add calendar name to output
        # User can manually filter in config by calendar names
        calendar_filter = self.config.get('calendar_filter', [])

        if calendar_filter:
            for cal in all_calendars:
                if cal.title() in calendar_filter:
                    calendars.append(cal)
        else:
            calendars = list(all_calendars)

        return calendars

    def fetch_events_for_date(self, date=None):
        """Fetch all events for a specific date."""
        if date is None:
            date = datetime.now()

        # Set time range for the entire day
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Convert to NSDate
        start_ns = NSDate.dateWithTimeIntervalSince1970_(start_of_day.timestamp())
        end_ns = NSDate.dateWithTimeIntervalSince1970_(end_of_day.timestamp())

        # Get calendars based on config
        calendar_set = self.config.get('calendar_set', 'all')
        calendars = self.get_calendar_set_calendars(calendar_set)

        if not calendars:
            print(f"Warning: No calendars found for set '{calendar_set}'")
            return []

        # Create predicate and fetch events
        predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
            start_ns, end_ns, calendars
        )
        events = self.store.eventsMatchingPredicate_(predicate)

        return list(events)

    def format_event_as_markdown(self, event):
        """Format a single event as markdown."""
        title = event.title() or "Untitled Event"
        calendar_name = event.calendar().title()

        # Determine tags (FYI/Optional) from config
        fyi_cals = set(self.config.get('fyi_calendars', []) or [])
        optional_keywords = [k.lower() for k in (self.config.get('optional_keywords', []) or [])]
        tags = []
        if calendar_name in fyi_cals:
            tags.append('FYI')
        lower_title = title.lower()
        if any(k in lower_title for k in optional_keywords):
            tags.append('Optional')

        # Format time
        start_date = event.startDate()
        end_date = event.endDate()

        # Convert NSDate to Python datetime
        start_time = datetime.fromtimestamp(start_date.timeIntervalSince1970())
        end_time = datetime.fromtimestamp(end_date.timeIntervalSince1970())

        if event.isAllDay():
            time_str = "All Day"
        else:
            time_str = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"

        # Build markdown
        tag_prefix = ''.join(f"[{t}]" for t in tags)
        display_title = f"{tag_prefix} {title}".strip()
        md = f"- **{time_str}** | {display_title}"

        # Add calendar name and optional label if configured
        if self.config.get('show_calendar_name', True):
            labels = self.config.get('calendar_labels', {}) or {}
            label = labels.get(calendar_name)
            if label:
                md += f" *(Calendar: {calendar_name} — {label})*"
            else:
                md += f" *(Calendar: {calendar_name})*"

        # Add location if available
        if event.location() and self.config.get('show_location', True):
            md += f"\n  - 📍 {event.location()}"

        # Add notes if available
        if event.notes() and self.config.get('show_notes', False):
            notes = event.notes().strip()
            if notes:
                md += f"\n  - 📝 {notes}"

        return md

    def generate_calendar_note(self, date=None):
        """Generate the full calendar note for a date."""
        if date is None:
            date = datetime.now()

        events = self.fetch_events_for_date(date)

        # Sort events by start time
        events.sort(key=lambda e: e.startDate().timeIntervalSince1970())

        # Build markdown content
        date_str = date.strftime('%A, %B %d, %Y')
        md_lines = [
            f"# Calendar for {date_str}",
            "",
            f"*Last updated: {datetime.now().strftime('%I:%M %p')}*",
            "",
        ]

        # Add context note if configured
        context_note = self.config.get('context_note', '')
        if context_note:
            md_lines.append(f"> {context_note}")
            md_lines.append("")

        # Legend if tagging is enabled
        if (self.config.get('fyi_calendars') or self.config.get('optional_keywords')):
            md_lines.append("Legend: [FYI] informational/not a direct commitment; [Optional] attendance not required.")
            md_lines.append("")

        if not events:
            md_lines.append("No events scheduled for today.")
        else:
            md_lines.append(f"**{len(events)} event(s) scheduled:**")
            md_lines.append("")

            fyi_count = 0
            optional_count = 0

            formatted = []
            for event in events:
                line = self.format_event_as_markdown(event)
                formatted.append(line)
                if "[FYI]" in line:
                    fyi_count += 1
                if "[Optional]" in line:
                    optional_count += 1

            md_lines.extend(formatted)

            # Summary block
            md_lines.append("")
            md_lines.append(f"Summary: {len(events)} total | {fyi_count} FYI | {optional_count} Optional")

        return "\n".join(md_lines)

    def get_note_path(self, date=None):
        """Get the path for the calendar note."""
        if date is None:
            date = datetime.now()

        vault_path = Path(self.config['obsidian_vault_path']).expanduser()
        note_name = self.config.get('calendar_note_name', 'Today\'s Calendar.md')

        # Support date formatting in note name
        note_name = date.strftime(note_name)

        note_path = vault_path / note_name

        # Create parent directories if they don't exist
        note_path.parent.mkdir(parents=True, exist_ok=True)

        return note_path

    def export_to_obsidian(self, date=None):
        """Export calendar to Obsidian note."""
        if date is None:
            date = datetime.now()

        content = self.generate_calendar_note(date)
        note_path = self.get_note_path(date)

        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ Calendar exported to: {note_path}")
        return note_path


def parse_date_arg(date_str):
    """Parse date argument into datetime object."""
    if not date_str:
        return None

    # Handle special keywords
    if date_str.lower() == "today":
        return datetime.now()
    elif date_str.lower() == "tomorrow":
        return datetime.now() + timedelta(days=1)
    elif date_str.lower() == "yesterday":
        return datetime.now() - timedelta(days=1)

    # Handle relative days (+1, -1, etc.)
    if date_str.startswith('+') or date_str.startswith('-'):
        try:
            days = int(date_str)
            return datetime.now() + timedelta(days=days)
        except ValueError:
            pass

    # Try parsing as date in various formats
    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: {date_str}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export calendar events to Obsidian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./cal_to_obsidian.py                    # Export today's calendar
  ./cal_to_obsidian.py --date tomorrow    # Export tomorrow's calendar
  ./cal_to_obsidian.py --date yesterday   # Export yesterday's calendar
  ./cal_to_obsidian.py --date +3          # Export 3 days from now
  ./cal_to_obsidian.py --date 2025-11-17  # Export specific date
  ./cal_to_obsidian.py -d 11/17/2025      # Also works with MM/DD/YYYY
  ./cal_to_obsidian.py --list-calendars   # Show all available calendars
        """
    )

    parser.add_argument(
        '-d', '--date',
        type=str,
        help='Date to export (today, tomorrow, yesterday, +N, -N, YYYY-MM-DD, MM/DD/YYYY)'
    )

    parser.add_argument(
        '--list-calendars',
        action='store_true',
        help='List all available calendars and exit'
    )

    args = parser.parse_args()

    # Check for config file
    env_cfg = os.environ.get("CAL2_CONFIG")
    if env_cfg:
        config_path = env_cfg
    else:
        # Default to config.yaml next to this script
        config_path = str(SCRIPT_DIR / "config.yaml")

    if not os.path.exists(config_path):
        print("No config.yaml found. Creating from example...")
        example_path = str(SCRIPT_DIR / "config.example.yaml")
        if os.path.exists(example_path):
            import shutil
            shutil.copy(example_path, config_path)
            print(f"Created {config_path}. Please edit it with your settings.")
            sys.exit(0)
        else:
            print("Error: config.example.yaml not found next to script!")
            print(f"Tried: {example_path}")
            sys.exit(1)

    # Handle list-calendars command
    if args.list_calendars:
        try:
            from EventKit import (
                EKAuthorizationStatusAuthorized,
                EKAuthorizationStatusNotDetermined,
                EKEventStore,
                EKEntityTypeEvent,
            )
            from Foundation import NSRunLoop, NSDate

            store = EKEventStore.alloc().init()
            status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)

            if status == EKAuthorizationStatusNotDetermined:
                finished = {'done': False}

                def _completion(granted, error):
                    finished['done'] = True

                store.requestAccessToEntityType_completion_(EKEntityTypeEvent, _completion)
                while not finished['done']:
                    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
                status = EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent)

            if status != EKAuthorizationStatusAuthorized:
                print("⚠️  Calendar access not authorized")
                print("Please enable access in System Settings → Privacy & Security → Calendars and retry.")
                sys.exit(1)

            calendars = store.calendarsForEntityType_(EKEntityTypeEvent)

            print("📅 Available Calendars:")
            print("=" * 60)

            for cal in calendars:
                print(f"\nCalendar: {cal.title()}")
                print(f"  Type: {cal.type()}")
                print(f"  Color: {cal.color()}")
                print(f"  Source: {cal.source().title()}")

                # Check if calendar has a specific account email
                source = cal.source()
                if hasattr(source, 'externalID'):
                    print(f"  Account: {source.externalID()}")

            print("\n" + "=" * 60)
            print("\nTo filter calendars, add them to 'calendar_filter' in config.yaml:")
            print("calendar_filter:")
            for cal in calendars:
                print(f'  - "{cal.title()}"')

            sys.exit(0)
        except Exception as e:
            print(f"❌ Error listing calendars: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # Parse date argument
    try:
        target_date = parse_date_arg(args.date) if args.date else None
        if target_date:
            print(f"📅 Exporting calendar for: {target_date.strftime('%A, %B %d, %Y')}")
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Run export
    try:
        exporter = CalendarExporter(config_path)
        exporter.export_to_obsidian(date=target_date)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
