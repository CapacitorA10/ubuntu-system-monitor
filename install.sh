#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
LAUNCHER="$BIN_DIR/ubuntu-system-monitor"
DESKTOP_FILE="$DESKTOP_DIR/ubuntu-system-monitor.desktop"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

mkdir -p "$BIN_DIR" "$DESKTOP_DIR"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$APP_DIR/app.py" "\$@"
EOF
chmod +x "$LAUNCHER"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Ubuntu System Monitor
Comment=CPU, Memory, Temperature and Storage Monitor
Exec=$LAUNCHER
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=System;Monitor;
StartupNotify=true
EOF
chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed: $LAUNCHER"
echo "Desktop entry: $DESKTOP_FILE"
echo "Run: ubuntu-system-monitor"
echo "Dock: 앱 검색에서 'Ubuntu System Monitor' 실행 후 Dock 우클릭 → 즐겨찾기에 추가"
