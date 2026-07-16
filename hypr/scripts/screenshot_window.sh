#!/bin/bash

# Get the geometry of the window that was focused before the screenshot command
# focusHistoryID: 1 is the window focused just before the current one.
WINDOW_INFO=$(hyprctl clients -j | jq -r '.[] | select(.focusHistoryID == 1)')
GEOMETRY=$(echo "$WINDOW_INFO" | jq -r '"\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"')
TITLE=$(echo "$WINDOW_INFO" | jq -r '.title')

if [ -z "$GEOMETRY" ] || [ "$GEOMETRY" == "null" ]; then
    notify-send "Screenshot Failed" "Could not find a previous window to capture."
    exit 1
fi

DEST="$HOME/Pictures/Screenshots/screenshot-$(date +%Y%m%d-%H%M%S).png"
mkdir -p "$HOME/Pictures/Screenshots"
grim -g "$GEOMETRY" "$DEST"
wl-copy --type image/png < "$DEST"
