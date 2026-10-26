# Native multiseat session

The native fork is in `~/caelestia-repo-work/hyprland-multiseat`, on
`feat/logical-multiseat`. See its `docs/native-multiseat.md` for architecture,
commands and limitations. The stock compositor and current configuration are
retained. This session runs the optimized compositor through the stock watchdog
with `--path`; no user session is terminated by installation.

At the login screen choose **Caelestia (native multiseat)**. Once logged in,
Super+M toggles native independent input. Built-in keyboard/touchpad operate
on eDP-1, external keyboard/mouse on HDMI-A-1. Toggle again to return to normal.
The feature starts disabled, and display disconnect/mirroring releases it.
Choose the ordinary **Hyprland** session at login for immediate recovery.

The launcher checks the recorded versions of the C++ Hyprland runtime libraries
and missing shared libraries before startup. On incompatibility it starts the
stock session instead of attempting an unsafe binary. Rebuild and rerun the
integration checks after native dependencies change. Updating the distribution
Hyprland package does not overwrite the installed fork or custom configuration.

Do not load the old nested-desktop pointer-guard plugin into this fork. Native
input owns its cursor bounds directly. The old paused nested session is left
alone until its owner has saved any work. This implementation is under local
verification; no upstream PR has been opened before the user's physical test.


The October 16 input recovery update also covers Electron embedded browser views.
The private regression fixture exercises real DOM typing, native context menus,
timestamp tooltips, Wayland-to-X11 text/PNG paste, modifier-held disable and
repeated resume cycles. X11 focus and selection requests resolve an active logical
seat, unmanaged popup geometry selects its output before layout clamps it, and
Xwayland receives fresh pointer enter coordinates after rebuilding seat devices.
A resumed seat synchronizes clipboard selections changed in ordinary mode.

The shell closes transient grabs before Super+M changes ownership. Terminal
launches recheck the current mode instead of trusting an old app environment.
The toggle helper allows disabling an older session but requires a new login
before enabling a newly installed compositor. Updating the package cannot replace
a compositor process that already owns the display; shell restart is insufficient.

Session actions run in a separate transient user service so shell teardown cannot
kill its own logout command. Logout first requests graceful compositor exit, then
cleans up the graphical target. Shutdown/reboot retain normal systemd inhibitor
handling. Commands remain configurable. Failure notifications and the latest
result in ~/.local/state/caelestia/session-action.json replace silent failures.
The session buttons show an activity icon while a request is pending. Tests use
substitute commands and a harmless worker; they never reboot or power off the host.
