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

systemctl --user reset-failed \
    xdg-desktop-portal.service \
    xdg-desktop-portal-hyprland.service \
    xdg-desktop-portal-gtk.service || true

# Start after Hyprland has exported WAYLAND_DISPLAY and DISPLAY. Starting the
# portal from an early default.target unit caused the GTK implementation to
# launch without a display and enter start-limit-hit.
systemctl --user start xdg-desktop-portal.service || true
