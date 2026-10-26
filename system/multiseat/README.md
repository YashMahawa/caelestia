# Independent desktops

For agent computer use while the human works on the monitor, use
`caelestia-agent-desktop status`, then `caelestia-agent-desktop start`.
It fills the **built-in laptop display**, regardless of current pointer focus.
See [../agent-desktop/README.md](../agent-desktop/README.md) and the installed
`caelestia-agent-desktop` skill for private mouse/keyboard/browser automation.
Pause when done; apps remain open. Builds use `caelestia-build`.

Super+M controls the separate **native two-person mode**, installed beside the
stock compositor. Choose **Caelestia (native multiseat)** at login to use it.
See [native/README.md](native/README.md). An agent must check current mode and
must not take over a laptop desktop already occupied by a second person.

`caelestia-multiseat test` is the lower-level isolated-desktop entry point.
It defaults to the laptop, exports private Wayland/Sway sockets, and its `exec --`
runs synchronously with a private bus and sanitized activation environment.
`pause` preserves apps; `stop` terminates them and is only appropriate after
saving their work. Testing never grabs devices, changes host focus, or loads the
old physical cursor-confinement plugin.

The physical-input bridge and pointer plugin here are retained for the earlier
nested implementation; they are not bound to Super+M and are unnecessary for
agent tests. Do not load that plugin into the native fork. Its ABI must match the
running compositor before any legacy physical-input use.

Logs: `journalctl --user -u caelestia-multiseat`. Both vendored protocol XMLs
retain their upstream licenses from swaywm/wlr-protocols and swaywm/wlroots.
