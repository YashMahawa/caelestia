# Private agent desktop

`caelestia-agent-desktop` gives agents a full built-in laptop display while the
human uses the external monitor. It is an isolated Sway session with private
Wayland, Xwayland, D-Bus, input, clipboard and app profiles. It never captures
physical input, loads a host pointer plugin, or dispatches host keyboard focus.
It is separate from Super+M's two-person native logical-seat mode.

Start with `caelestia-agent-desktop status`, then `start`. The display is selected
by its built-in eDP/LVDS name, not by focus. `pause` hides it and preserves apps.
The agent must leave an occupied two-person desktop alone. Unplug/mirror pauses
it; every computer-use command checks live mode and private sockets again.

Install `bin/caelestia-agent-desktop` and `bin/caelestia-multiseat` in `~/.local/bin`.
Build virtual input with `caelestia-build -- system/agent-desktop/build.sh`.
Dependencies: Python, Sway, wl-clipboard, wtype, grim, Wayland/xkbcommon development
files; Chrome or another supported browser is optional. `xdg-dbus-proxy` allows
only Secret Service access when a copied Chrome profile needs its encryption key;
host app activation and portals remain filtered out of that browser connection.

The shared skill in `skills/caelestia-agent-desktop` documents native and browser
computer use. Install it in `~/.codex/skills`, `~/.claude/skills`,
`~/.gemini/config/skills`, and `~/.gemini/antigravity-cli/skills`. These can be
symlinks to the canonical repository copy. Its controls reference is the CLI
quick reference; `--help` and each subcommand's `--help` describe arguments.

Chrome/Electron/Firefox launches get private profiles, avoiding process-singleton
handoff to the monitor. A local `~/.config/caelestia/agent-desktop.json` can select
a copied Chrome profile (`chromeProfileRoot`, `chromeProfileDirectory`). The root
must be under `~/.local/share/caelestia/agent-desktop`. Original profile databases
must never be symlinked or shared live. `browser` exposes a verified localhost CDP
endpoint for the private compositor's Chrome process, including subsequent calls
that reuse that process. Account-specific preferences are not stored in Git.

The persistent virtual keyboard/pointer avoids first-event loss as applications
bind seat capabilities. Test-mode Sway has one seat and leaves parent physical
devices unassigned, so Chromium and GTK do not accidentally bind another keyboard.
Screenshots and input use private screenshot coordinates, including exact corners.
The host surface has a fixed borderless size matching the laptop output, with
render-unfocused enabled. It is not tied to the host's keyboard fullscreen state:
focusing a host app would otherwise undo fullscreen and restore the original
1280×720 size. Existing rules are reused instead of replaced during refresh;
removing a previous rule can asynchronously undo the replacement rule's state.

Routing unit tests: `python -m unittest discover -s tests -p test_agent_desktop.py`.
Runtime tests should cover real native widgets, browser typing/modifiers, pointer
scroll/drag/context menu, text/image paste, pause/resume, missing sockets, display
removal, window sizing and host focus preservation. Do not exercise real power,
logout or destructive user actions as GUI fixtures.
