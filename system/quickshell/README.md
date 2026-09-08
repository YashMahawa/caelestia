# Quickshell screen lifetime fix

This package pins the previously installed upstream revision and retains removed
screen wrappers until the shell exits. Physical QScreen objects are still released
normally. The wrapper's existing `screenDestroyed()` handler clears its pointer.

Deleting the wrapper during hotplug notifies QML bindings while output delegates
and their windows are being torn down. On this Qt 6.11.2 installation, production
cores show `QuickshellScreenInfo::~QuickshellScreenInfo` leading through QML
geometry bindings to a SIGSEGV in `QQuickWindow::maybeUpdate`. Other cores show
item teardown at the same display transition.

The old patch existed in a separate build directory but was absent from the
installed 0.3.1.r10.g2d3b3e9-1 binary. Package release 2 includes it. Verify the
actual packaged/installed executable, rather than assuming source edits are live.

This trades a small screen-wrapper allocation per output removal for stable QML
references. It does not retain physical displays or their framebuffers, and adds
no polling service. Revisit retention when an upstream lifetime fix is available.

## Build and verification

Run `makepkg` in this directory. The build uses two compiler jobs. Install the
resulting package with pacman and restart the shell only when its service has no
unrelated applications in its cgroup. Keep the existing package/binary for rollback.

The test files use Qt's offscreen platform and synthesize 100 output add/remove
cycles. Compile the C++ file as a shared library using Qt6Gui and Qt6Core, including
their version-specific private include directories. Run the test QML with that
library in LD_PRELOAD, QT_QPA_PLATFORM=offscreen, QT_QUICK_BACKEND=software,
QS_DISABLE_CRASH_HANDLER=1, and a separate XDG_RUNTIME_DIR. The library refuses
to run on a real display backend. Never preload it into the desktop shell.

Validation on 2026-09-08:

- Both old and patched executables completed the corrected 100-cycle offscreen test.
- The old executable produced null screen-property errors during delegate teardown;
  the patched executable produced none of those errors.
- Disassembly of `QuickshellTracked::updateScreens()` confirms the installed
  replacement has no `QObject::deleteLater()` call.
- Qt compatibility check passed, installed and packaged binary hashes matched,
  and the live Caelestia configuration loaded successfully after restart.
- Physical suspend/resume was not triggered; confirmation on real monitor resume
  remains necessary. The offscreen test does not reproduce the complete production
  compositor/rendering environment.

An initial test harness erroneously deleted QPlatformScreen a second time after
`handleScreenRemoved`; those crashes are invalid test results. The checked-in
test uses Qt's ownership correctly.
