#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p build
exec 9>build/build.lock
flock 9
trap 'rm -f "build/input-bridge.new.$$" "build/pointer-guard.new.$$.so" "build/hyprland-version.new.$$"' EXIT
for name in virtual-keyboard-unstable-v1 wlr-virtual-pointer-unstable-v1; do
    wayland-scanner client-header "protocols/$name.xml" "build/$name-client-protocol.h"
    wayland-scanner private-code "protocols/$name.xml" "build/$name-protocol.c"
done
cc -O2 -Wall -Wextra -Werror -Ibuild input-bridge.c build/*-protocol.c $(pkg-config --cflags --libs libinput wayland-client xkbcommon) -o "build/input-bridge.new.$$"
g++ -std=c++26 -O2 -shared -fPIC -Wno-unused-parameter $(pkg-config --cflags hyprland) pointer-guard.cpp -o "build/pointer-guard.new.$$.so"
/usr/bin/Hyprland --version-json > "build/hyprland-version.new.$$"
# A running compositor may still map the old plugin. Replace its inode;
# never truncate an in-use shared library during an update.
mv -f "build/input-bridge.new.$$" build/input-bridge
mv -f "build/pointer-guard.new.$$.so" build/pointer-guard.so
mv -f "build/hyprland-version.new.$$" build/hyprland-version.json
