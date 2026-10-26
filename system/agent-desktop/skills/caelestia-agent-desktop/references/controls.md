# Private desktop controls

```sh
caelestia-agent-desktop status
caelestia-agent-desktop start
caelestia-agent-desktop launch -- my-app --new-instance
caelestia-agent-desktop exec -- command-that-should-finish
caelestia-agent-desktop windows
caelestia-agent-desktop focus 5
caelestia-agent-desktop screenshot /absolute/task/path/screen.png
caelestia-agent-desktop click 400 300
caelestia-agent-desktop click 400 300 --button right
caelestia-agent-desktop click 400 300 --count 2
caelestia-agent-desktop move 0 0
caelestia-agent-desktop drag 100 100 700 500 --duration 0.6
caelestia-agent-desktop scroll 3
caelestia-agent-desktop scroll -2 --horizontal
caelestia-agent-desktop type 'Unicode text ✓'
printf '%s' 'text from a script' | caelestia-agent-desktop type
caelestia-agent-desktop key ctrl+a
caelestia-agent-desktop key ctrl+shift+p
caelestia-agent-desktop key enter
caelestia-agent-desktop clipboard set 'private clipboard text'
caelestia-agent-desktop clipboard get
caelestia-agent-desktop clipboard set-image /absolute/task/path/screen.png
caelestia-agent-desktop clipboard types
caelestia-agent-desktop browser http://127.0.0.1:3000
caelestia-agent-desktop pause
```

Positive scrolling moves down/right. Drag uses interpolated motion with a held button; modifiers release after a chord. Typing uses Wayland Unicode input, leaving the clipboard unchanged. The virtual keyboard/pointer persists across commands to avoid losing first events. Host keyboards/mice are not attached to the private test seat.

`exec` returns the command's real stdout and exit status; use `launch` for a long-running GUI. `windows` returns private IDs and geometry; `focus` affects only those windows. Private app logs rotate at 5 MiB plus one previous log.

Browser example (with an installed Playwright library):

```js
const browser = await chromium.connectOverCDP(cdpEndpoint);
const pages = browser.contexts()[0].pages();
// Select the test page by its verified URL; leave unrelated tabs alone.
await pages[0].screenshot({ path: '/absolute/task/path/browser.png' });
await browser.close(); // disconnect the CDP client; do not kill human browsers
```

The CLI has no general host-input mode and does not grant new permissions for accounts, messages, purchases or destructive actions. Route private clipboard tools with `exec --`; ordinary host `wl-copy`/`wl-paste` target a different clipboard.
