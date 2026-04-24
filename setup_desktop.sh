#!/bin/sh
set -e

echo "[setup_desktop] Running setup_desktop.sh"

HOME_DIR=/home/jovyan
SRC_DIR=/opt/shortcuts
DESKTOP_DIR="$HOME_DIR/Desktop"

###############################################################################
# 1. .condarc setup
# Originally sourced from L1NNA/L1NNA-peppapig; content is now embedded here
# so the script has no external dependency on that repo.
###############################################################################

cat > "$HOME_DIR/.condarc" << "EOF"
envs_dirs:
  - /home/jovyan/conda-envs/
EOF

sudo tee /opt/conda/.condarc > /dev/null << "EOF"
channels:
  - defaults
auto_update_conda: false
show_channel_urls: true
channel_priority: strict
EOF

###############################################################################
# 2. Disable XFCE logout so users can't kill the VNC desktop (run as root)
###############################################################################

if command -v xfce4-session-logout >/dev/null 2>&1; then
  if [ ! -f /usr/bin/xfce4-session-logout.real ]; then
    echo "[setup_desktop] Wrapping xfce4-session-logout"
    mv /usr/bin/xfce4-session-logout /usr/bin/xfce4-session-logout.real
    cat > /usr/bin/xfce4-session-logout << "EOF"
#!/bin/sh
echo "Logout is disabled in this environment." >&2
exit 0
EOF
    chmod +x /usr/bin/xfce4-session-logout
  else
    echo "[setup_desktop] xfce4-session-logout already wrapped"
  fi
else
  echo "[setup_desktop] xfce4-session-logout not found; skipping logout wrap"
fi

###############################################################################
# 3. Create shortcuts and desktop entries (no use of ~/.local)
###############################################################################

echo "[setup_desktop] Ensuring dirs: $SRC_DIR, $DESKTOP_DIR"
mkdir -p "$SRC_DIR" "$DESKTOP_DIR"

# 3a. Launcher templates under /opt/shortcuts (source copies)

if [ ! -f "$SRC_DIR/code.desktop" ]; then
  echo "[setup_desktop] Creating $SRC_DIR/code.desktop"
  cat > "$SRC_DIR/code.desktop" << "EOF"
[Desktop Entry]
Type=Application
Name=Visual Studio Code
Comment=Code Editing. Redefined.
Exec=/usr/share/code/code %F
Icon=vscode
Terminal=false
Categories=TextEditor;Development;IDE;
EOF
fi

if [ ! -f "$SRC_DIR/matlab.desktop" ]; then
  echo "[setup_desktop] Creating $SRC_DIR/matlab.desktop"
  cat > "$SRC_DIR/matlab.desktop" << "EOF"
[Desktop Entry]
Type=Application
Name=MATLAB
Comment=Start MATLAB
# Optionally show MATLAB in a terminal for feedback; adjust as you prefer:
#Exec=xfce4-terminal -e "matlab -desktop"
Exec=matlab -desktop
Icon=matlab
Terminal=true
Categories=Development;Science;
EOF
fi

chmod +x "$SRC_DIR"/code.desktop "$SRC_DIR"/matlab.desktop || true
chown jovyan:users "$SRC_DIR"/code.desktop "$SRC_DIR"/matlab.desktop || true

# 3b. Copy launchers directly onto the Desktop, if missing

# VS Code on Desktop
if [ ! -f "$DESKTOP_DIR/code.desktop" ]; then
  echo "[setup_desktop] Installing VS Code launcher to $DESKTOP_DIR"
  cp "$SRC_DIR/code.desktop" "$DESKTOP_DIR/code.desktop"
fi

# MATLAB on Desktop
if [ ! -f "$DESKTOP_DIR/matlab.desktop" ]; then
  echo "[setup_desktop] Installing MATLAB launcher to $DESKTOP_DIR"
  cp "$SRC_DIR/matlab.desktop" "$DESKTOP_DIR/matlab.desktop"
fi

chmod +x "$DESKTOP_DIR"/code.desktop "$DESKTOP_DIR"/matlab.desktop || true
chown jovyan:users "$DESKTOP_DIR"/code.desktop "$DESKTOP_DIR"/matlab.desktop || true

###############################################################################
# 4. Fix ownership only for files we touched
###############################################################################

# .condarc
if [ -f "$HOME_DIR/.condarc" ]; then
  chown jovyan:users "$HOME_DIR/.condarc" || true
fi

# Desktop and /opt/shortcuts
#[ -d "$DESKTOP_DIR" ] && chown -R jovyan:users "$DESKTOP_DIR" || true
#[ -d "$SRC_DIR" ] && chown -R jovyan:users "$SRC_DIR" || true
# Desktop and /opt/shortcuts
# not having the -R broke this because the desktop icon was still owned by root. moved chown to after the copy.
#[ -d "$DESKTOP_DIR" ] && chown  jovyan:users "$DESKTOP_DIR" || true
#[ -d "$SRC_DIR" ] && chown  jovyan:users "$SRC_DIR" || true


###############################################################################
# 5. Ensure TurboVNC config exists for Blackwell GPU compatibility
###############################################################################

if [ ! -f "$HOME_DIR/.vnc/turbovncserver.conf" ]; then
  echo "[setup_desktop] Creating TurboVNC config for Blackwell GLX fix"
  mkdir -p "$HOME_DIR/.vnc"
  echo '$serverArgs = "-extension GLX";' > "$HOME_DIR/.vnc/turbovncserver.conf"
  chown -R jovyan:users "$HOME_DIR/.vnc"
else
  echo "[setup_desktop] TurboVNC config already exists, skipping"
fi

echo "[setup_desktop] Done"
