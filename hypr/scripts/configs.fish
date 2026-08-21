#!/usr/bin/env fish

set -l _reload false

# Ensure config directory exists
if ! test -d $argv[1]
    mkdir -p $argv[1]
end

# Ensure hypr-vars exists
if ! test -f $argv[1]/hypr-vars.conf
    touch -a $argv[1]/hypr-vars.conf
    set -l _reload true
end

# Ensure hypr-user exists
if ! test -f $argv[1]/hypr-user.conf
    touch -a $argv[1]/hypr-user.conf
    set -l _reload true
end

# Run startup rule syntax validation on core system rules and user override files
set -l script_dir (dirname (status filename))
if test -f $script_dir/validate_rules.py
    python3 $script_dir/validate_rules.py $script_dir/../hyprland/rules.conf $argv[1]/hypr-user.conf
end

# Reload as needed
if _reload
    hyprctl reload
end
