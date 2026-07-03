#!/usr/bin/env bash

set -u

window=$(hyprctl activewindow -j) || exit 1
address=$(jq -r '.address // empty' <<<"$window")
was_floating=$(jq -r '.floating // false' <<<"$window")
read -r x y < <(jq -r '.at | @tsv' <<<"$window")

[[ -n "$address" && "$x" != "null" && "$y" != "null" ]] || exit 0

hyprctl dispatch togglefloating "address:$address" >/dev/null || exit 1

if [[ "$was_floating" == "false" ]]; then
    is_floating=$(hyprctl clients -j | jq -r --arg address "$address" '.[] | select(.address == $address) | .floating')
    if [[ "$is_floating" == "true" ]]; then
        hyprctl dispatch movewindowpixel "exact $x $y,address:$address" >/dev/null
    fi
fi
