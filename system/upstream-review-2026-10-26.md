# Compatible upstream review — 2026-10-26

Reviewed caelestia-dots/caelestia through `b476a36` and caelestia-dots/shell through
`4b1dae84`, fetched from their original GitHub remotes. Kept the installed theme,
custom lyrics/artwork/search, settings extensions, recording and seat routing.

Backported to the shell fork and installed locally:

- `a17d58cd`: notify QML after updating `hasLyrics`, avoid duplicate clear signals.
- `f7447a81`: detect the physical Caps Lock key with remapped keyboard layouts.
- `4ffb060a`: display calculator uncertainty intervals using significant digits,
  applied to both synchronous and asynchronous evaluation in this fork.
- `588562ea`: do not instantiate the session animation when its configured path
  is empty; retain the custom session action/error handling.

The build and three existing CTest checks passed. Plugin libraries were staged
and atomically replaced, then the installed shell restarted successfully. Only
new backport hunks were committed for files with unrelated local modifications.

Several original-dotfiles improvements were already present locally, including
Foot alpha matching and floating file rename dialogs. Picture-in-picture behavior
was deliberately not reset: this fork disables its automatic floating rule.
The recent upstream Lua configuration migration, shell state/config restructuring,
wallpaper/video implementation and namespace/component rewrites are not drop-in
changes for this customised installation; no blanket merge was performed.

Also added the private laptop agent desktop CLI and shared skill in
`system/agent-desktop`. Native cursor isolation fixes are maintained in the local
Hyprland fork at `9ff8266`; a reproducible source patch and tests are retained in
`system/multiseat/native/patches`. Its optimized package installs beside the stock
compositor and requires a new native-session login to activate. No running
compositor is replaced during installation, and no upstream Hyprland PR is opened
before the user's physical verification.
