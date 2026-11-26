#!/bin/bash
# Install launchd automation for daily calendar export

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_NAME="com.user.cal-to-obsidian"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "🤖 Installing automation for Fantastical to Obsidian..."

# Choose Python interpreter (prefer Frameworks build if present to match granted TCC perms)
FRAMEWORK_PY="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if [ -x "$FRAMEWORK_PY" ]; then
  PYTHON_PATH="$FRAMEWORK_PY"
else
  PYTHON_PATH=$(which python3)
fi

# Test the script first to ensure calendar permissions are granted
# IMPORTANT: use the exact interpreter path that launchd will use so TCC grants the right binary
echo "📋 Testing script and checking permissions (interpreter: ${PYTHON_PATH})..."
if ! "${PYTHON_PATH}" "${SCRIPT_DIR}/cal_to_obsidian.py" --list-calendars > /dev/null 2>&1; then
    echo ""
    echo "❌ The script doesn't have calendar access yet for: ${PYTHON_PATH}"
    echo ""
    echo "To fix this, grant Calendar permissions to that exact Python binary:"
    echo "1) Run: \"${PYTHON_PATH}\" \"${SCRIPT_DIR}/cal_to_obsidian.py\""
    echo "2) When prompted, click OK to allow calendar access"
    echo "3) System Settings → Privacy & Security → Calendars: ensure Python has access"
    echo "4) Re-run this installer"
    echo ""
    exit 1
fi

echo "✅ Calendar permissions verified!"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Create the plist file
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SCRIPT_DIR}/cal_to_obsidian.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>StartCalendarInterval</key>
    <array>
        <!-- Run at 6:00 AM -->
        <dict>
            <key>Hour</key>
            <integer>6</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Run at 9:00 AM -->
        <dict>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Run at 12:00 PM -->
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <!-- Run at 6:00 PM -->
        <dict>
            <key>Hour</key>
            <integer>18</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/logs/output.log</string>

    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/logs/error.log</string>

    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

# Create logs directory
mkdir -p "${SCRIPT_DIR}/logs"

# Load the launch agent (use modern bootstrap/kickstart for reliability)
echo "📋 Loading launch agent..."
launchctl bootout gui/"$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap gui/"$(id -u)" "$PLIST_PATH"
launchctl kickstart -k gui/"$(id -u)"/${PLIST_NAME}

echo ""
echo "✅ Automation installed successfully!"
echo ""
echo "The calendar will be exported automatically at:"
echo "  - 6:00 AM"
echo "  - 9:00 AM"
echo "  - 12:00 PM"
echo "  - 6:00 PM"
echo ""
echo "Logs are stored in: ${SCRIPT_DIR}/logs/"

echo ""
echo "📝 Troubleshooting tips:"
echo "  - If you change Python versions, re-run this installer to refresh the interpreter path"
echo "  - Verify status: launchctl print gui/\"$(id -u)\"/${PLIST_NAME} | sed -n '1,120p'"

echo ""
echo "Commands:"
echo "  Manual run (exact interpreter): ${PYTHON_PATH} ${SCRIPT_DIR}/cal_to_obsidian.py"
echo "  View logs: tail -f ${SCRIPT_DIR}/logs/output.log"
echo "  Uninstall: launchctl bootout gui/\"$(id -u)\" ${PLIST_PATH} && rm ${PLIST_PATH}"
echo ""
