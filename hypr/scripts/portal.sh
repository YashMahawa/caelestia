#!/bin/bash
set -euo pipefail

# Keep login fast: avoid force-restarting portals while Caelestia is painting.
# Systemd/socket activation will start these on demand; this script only cleans
# up failed portal units from an earlier broken session.
dbus-update-activation-environment --systemd \
    WAYLAND_DISPLAY \
    XDG_CURRENT_DESKTOP \
    XDG_SESSION_TYPE \
    XDG_SESSION_DESKTOP \
    HYPRLAND_INSTANCE_SIGNATURE || true

systemctl --user start hyprland-session-anchor.service || true

# Pre-flight check on user portal configuration: validate malformed installed config if present,
# but fall back to normal portal startup when absent or malformed.
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/xdg-desktop-portal"
portal_config=""
if [[ -f "$config_dir/hyprland-portals.conf" ]]; then
    portal_config="$config_dir/hyprland-portals.conf"
elif [[ -f "$config_dir/portals.conf" ]]; then
    portal_config="$config_dir/portals.conf"
fi

if [[ -n "$portal_config" ]]; then
    if ! grep -q "^\[preferred\]" "$portal_config" 2>/dev/null; then
        echo "Warning: Portal configuration file $portal_config is malformed (missing [preferred] section). Falling back to default portal startup." >&2
    fi
else
    echo "Notice: Custom portal configuration file not found in $config_dir. Falling back to default portal startup." >&2
fi

systemctl --user reset-failed \
    xdg-desktop-portal.service \
    xdg-desktop-portal-hyprland.service \
    xdg-desktop-portal-gtk.service || true

# Start after Hyprland has exported WAYLAND_DISPLAY and DISPLAY. Starting the
# portal from an early default.target unit caused the GTK implementation to
# launch without a display and enter start-limit-hit.
systemctl --user start xdg-desktop-portal.service || true
