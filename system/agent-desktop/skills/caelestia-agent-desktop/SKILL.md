---
name: caelestia-agent-desktop
description: Test native apps, websites and desktop workflows on Caelestia's private laptop display while the user works on the monitor. Use for interactive computer use, app launching, screenshots, clicks, typing, scrolling, dragging and browser automation on this laptop.
---

# Caelestia Agent Desktop

Check the live mode before starting GUI work:

```sh
caelestia-agent-desktop status
```

`hostMode` distinguishes `single-cursor` from `multi-cursor`. A native two-person session shares the compositor socket; it is **not** the private agent desktop. If multi-cursor mode is active, do not replace the laptop person's desktop or toggle their mode. Continue noninteractive work and ask about a free display if GUI testing is necessary.

In single-cursor mode, start or resume the isolated desktop:

```sh
caelestia-agent-desktop start
```

This explicitly targets the built-in laptop display, fills the display, and retains apps when paused. It does not choose the display based on pointer focus. Require `inputReady: true`; check status again after a pause, mode change or disconnect. The CLI refuses input when the private session is unavailable. Super+M pauses the private test desktop before enabling native two-person mode, preserving its apps. Never substitute host/global input as a fallback.

Use the CLI for native computer use. Run `caelestia-agent-desktop --help` or read [references/controls.md](references/controls.md) for commands. Coordinates are pixels in the **private screenshot**, not combined-monitor coordinates. Inspect screenshots/window geometry before clicking.

Launch GUI processes through `launch` or synchronous `exec --`. A process that reuses an existing instance can escape routing: supported Chrome/Electron/Firefox commands receive private profiles; use app-specific separate-instance/profile options for others. Chrome's configured laptop profile is an isolated copy of the user's selected profile. Do not modify the original profile or share its running database files.

For browser automation, `browser URL` returns a localhost CDP endpoint. Call `browser` without a URL to reuse its connection without opening another tab. Close the disposable tabs you create after testing; do not accumulate blank tabs. Connect Playwright/CDP to that endpoint, verify the browser's private screenshot/window, and use only its pages. A browser/computer-use tool that cannot explicitly target this private browser or compositor must not control the user's desktop. Do not open a generic browser tab through another tool and assume it belongs to the laptop.

Keep terminal-only compilation separate from GUI routing: use `caelestia-build -- COMMAND...` for builds so RAM and CPU remain budgeted. Before changing an installed component, follow its repository instructions.

When finished, close only your disposable test apps and run:

```sh
caelestia-agent-desktop pause
```

Pause preserves the desktop's remaining apps. Do not stop a session containing unsaved human work. Keep screenshots/logs in the task workspace and report test results without exposing browser tokens or unrelated personal content.
