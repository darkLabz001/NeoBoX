#!/usr/bin/env bash
# Provision a Raspberry Pi (Kali + Waveshare Game HAT) as a NeoBoX kiosk.
# Idempotent — safe to re-run. Run ON THE PI:  sudo bash ~/neo/scripts/setup-device.sh
set -euo pipefail

USER_NAME="${SUDO_USER:-kali}"
HOME_DIR="$(eval echo "~$USER_NAME")"
NEO="$HOME_DIR/neo"

echo "[1/5] passwordless sudo (so root payloads run on the handheld)"
cat > /etc/sudoers.d/neo <<SUDO
$USER_NAME ALL=(ALL) NOPASSWD: ALL
SUDO
chmod 440 /etc/sudoers.d/neo
visudo -cf /etc/sudoers.d/neo >/dev/null

echo "[2/5] kiosk: disable desktop chrome, show splash bridge via swaybg"
command -v swaybg >/dev/null || apt-get install -y swaybg
cat > /etc/xdg/labwc/autostart <<AUTO
# NeoBoX kiosk: no desktop. swaybg shows the splash until the UI renders.
swaybg -i $NEO/assets/backgrounds/boot_splash.png -m fill &
AUTO

echo "[3/5] user autostart launches NeoBoX"
install -d -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.config/labwc"
cat > "$HOME_DIR/.config/labwc/autostart" <<USERAUTO
# NeoBoX firmware autostart
$NEO/launch.sh &
USERAUTO
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/.config/labwc/autostart"

echo "[4/5] Plymouth NeoBoX boot splash"
install -d /usr/share/plymouth/themes/neobox
cp "$NEO/assets/backgrounds/neobox.png" /usr/share/plymouth/themes/neobox/neobox.png
cat > /usr/share/plymouth/themes/neobox/neobox.plymouth <<PLY
[Plymouth Theme]
Name=NeoBoX
Description=NeoBoX boot splash
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/neobox
ScriptFile=/usr/share/plymouth/themes/neobox/neobox.script
PLY
cat > /usr/share/plymouth/themes/neobox/neobox.script <<'SCR'
Window.SetBackgroundTopColor(0.02, 0.03, 0.05);
Window.SetBackgroundBottomColor(0.01, 0.02, 0.04);
logo.image = Image("neobox.png");
sw = Window.GetWidth(); sh = Window.GetHeight();
iw = logo.image.GetWidth(); ih = logo.image.GetHeight();
scale = sw / iw; if (sh / ih < scale) { scale = sh / ih; }
logo.scaled = logo.image.Scale(iw * scale, ih * scale);
logo.sprite = Sprite(logo.scaled);
logo.sprite.SetX((sw - iw * scale) / 2);
logo.sprite.SetY((sh - ih * scale) / 2);
SCR
/usr/sbin/plymouth-set-default-theme -R neobox

echo "[5/5] force 640x480 from KMS init (HAT panel; avoids scaler re-sync black)"
CMD=/boot/firmware/cmdline.txt
grep -q "video=HDMI" "$CMD" || sed -i '1 s/$/ video=HDMI-A-1:640x480M@60/' "$CMD"

echo "[6/6] games: Doom engine, RetroArch, Mednafen, uinput bridge deps"
apt-get install -y chocolate-doom freedoom retroarch retroarch-assets libretro-core-info mednafen python3-evdev python3-pip python3-flask python3-flask-socketio python3-eventlet || true
pip3 install -r "$NEO/requirements-web.txt" --break-system-packages || true
# Ensure firewall allows the web UI port
command -v ufw >/dev/null && ufw allow 8888/tcp || true
modprobe uinput || true; echo uinput > /etc/modules-load.d/uinput.conf

echo "Done. Reboot to apply."
