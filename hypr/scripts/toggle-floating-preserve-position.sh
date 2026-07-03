#!/usr/bin/env bash

set -u

window=$(hyprctl activewindow -j) || exit 1
address=$(jq -r '.address // empty' <<<"$window")
was_floating=$(jq -r '.floating // false' <<<"$window")
monitor_id=$(jq -r '.monitor // 0' <<<"$window")
read -r x y < <(jq -r '.at | @tsv' <<<"$window")

[[ -n "$address" && "$x" != "null" && "$y" != "null" ]] || exit 0

hyprctl dispatch togglefloating "address:$address" >/dev/null || exit 1

if [[ "$was_floating" == "false" ]]; then
    client=$(hyprctl clients -j | jq -c --arg address "$address" '.[] | select(.address == $address)')
    is_floating=$(jq -r '.floating // false' <<<"$client")
    if [[ "$is_floating" == "true" ]]; then
        read -r width height < <(jq -r '.size | @tsv' <<<"$client")
        monitor=$(hyprctl monitors -j | jq -c --argjson id "$monitor_id" '.[] | select(.id == $id)')
        if [[ -n "$monitor" ]]; then
            read -r mon_x mon_y mon_width mon_height reserved_left reserved_top reserved_right reserved_bottom < <(
                jq -r '[.x, .y, .width, .height, .reserved[0], .reserved[1], .reserved[2], .reserved[3]] | @tsv' <<<"$monitor"
            )
            margin=12
            min_x=$((mon_x + reserved_left + margin))
            min_y=$((mon_y + reserved_top + margin))
            usable_width=$((mon_width - reserved_left - reserved_right - margin * 2))
            usable_height=$((mon_height - reserved_top - reserved_bottom - margin * 2))
            if ((width > usable_width || height > usable_height)); then
                ((width > usable_width)) && width=$usable_width
                ((height > usable_height)) && height=$usable_height
                hyprctl dispatch resizewindowpixel "exact $width $height,address:$address" >/dev/null
            fi
            max_x=$((mon_x + mon_width - reserved_right - margin - width))
            max_y=$((mon_y + mon_height - reserved_bottom - margin - height))
            ((max_x < min_x)) && max_x=$min_x
            ((max_y < min_y)) && max_y=$min_y
            ((x < min_x)) && x=$min_x
            ((y < min_y)) && y=$min_y
            ((x > max_x)) && x=$max_x
            ((y > max_y)) && y=$max_y
        fi
        hyprctl dispatch movewindowpixel "exact $x $y,address:$address" >/dev/null
    fi
fi
