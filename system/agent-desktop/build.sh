#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
mkdir -p build
for name in virtual-keyboard-unstable-v1 wlr-virtual-pointer-unstable-v1; do
    wayland-scanner client-header "../multiseat/protocols/$name.xml" "build/$name-client-protocol.h"
    wayland-scanner private-code "../multiseat/protocols/$name.xml" "build/$name-protocol.c"
done
cc -O2 -Wall -Wextra -Werror -Ibuild input.c build/*-protocol.c $(pkg-config --cflags --libs wayland-client xkbcommon) -o build/input.new
mv build/input.new build/input
