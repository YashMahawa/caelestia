#!/usr/bin/env fish

set -l _reload false
set -l _config_dir $argv[1]

if test -z "$_config_dir"
    set _config_dir "$HOME/.config/caelestia"
end

# Ensure config directory exists
if ! test -d $_config_dir
    mkdir -p $_config_dir
end

# Ensure hypr-vars exists
if ! test -f $_config_dir/hypr-vars.conf
    touch -a $_config_dir/hypr-vars.conf
    set -l _reload true
end

# Ensure user override hypr-user.conf exists (preserve user override)
if ! test -f $_config_dir/hypr-user.conf
    touch -a $_config_dir/hypr-user.conf
    set -l _reload true
end

# Ensure user override hypr-user.lua exists if lua mode active (preserve user override)
set -l script_dir (dirname (status filename))
if test -f $_config_dir/hyprland.lua; or test -f $script_dir/../hyprland/rules.lua
    if ! test -f $_config_dir/hypr-user.lua
        touch -a $_config_dir/hypr-user.lua
        set -l _reload true
    end
end

# Run startup rule syntax validation on core system rules and user override files
if test -f $script_dir/validate_rules.py
    python3 $script_dir/validate_rules.py $script_dir/../hyprland/rules.conf $_config_dir/hypr-user.conf
    if test -f $script_dir/../hyprland.lua
        python3 $script_dir/validate_rules.py --lua $script_dir/../hyprland.lua
    end
    if test -f $script_dir/../hyprland/rules.lua
        python3 $script_dir/validate_rules.py --lua $script_dir/../hyprland/rules.lua $_config_dir/hypr-user.lua
    end
end

# Reload as needed
if $_reload
    hyprctl reload
end
