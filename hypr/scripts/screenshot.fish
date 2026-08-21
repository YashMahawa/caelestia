#!/usr/bin/env fish

function check_bin -a bin
    if not type -q $bin
        if type -q notify-send
            notify-send -a "caelestia-cli" "Missing utility: $bin" "Required binary '$bin' is not installed."
        end
        exit 1
    end
end

check_bin grim
check_bin wl-copy

set -l mode region
if test (count $argv) -ge 1
    set mode $argv[1]
end

set -l pictures_dir $HOME/Pictures
if set -q XDG_PICTURES_DIR
    set pictures_dir $XDG_PICTURES_DIR
end

set -l screenshots_dir "$pictures_dir/Screenshots"
mkdir -p $screenshots_dir

set -l dest "$screenshots_dir/"(date +%Y-%m-%d_%H-%M-%S-%3N)".png"

switch $mode
    case region area
        check_bin slurp
        set -l geometry (slurp 2>/dev/null)
        if test -z "$geometry"
            exit 1
        end
        grim -g "$geometry" "$dest"
    case full fullscreen screen
        check_bin hyprctl
        check_bin jq
        # Capture the focused monitor at its native pixel dimensions.  Unlike
        # selecting the whole screen in the area picker, this does not lose
        # edge pixels, and PNG remains fully lossless.
        set -l monitor (hyprctl monitors -j | jq -r '.[] | select(.focused) | .name' | head -n 1)
        if test -z "$monitor" -o "$monitor" = null
            exit 1
        end
        grim -o "$monitor" "$dest"
    case '*'
        echo "Usage: screenshot.fish [region|full]" >&2
        exit 1
end

or exit 1

wl-copy --type image/png < "$dest"
notify-send -a caelestia-cli -i "$dest" "Screenshot saved" "Saved losslessly to $dest and copied to clipboard"
