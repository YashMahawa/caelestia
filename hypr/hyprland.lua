-- Hyprland 0.55+ Authoritative Lua Configuration Entrypoint for Caelestia
-- Sourced by Hyprland at ~/.config/hypr/hyprland.lua

local config_dir = os.getenv("XDG_CONFIG_HOME") or ((os.getenv("HOME") or "") .. "/.config")
local hypr_dir = config_dir .. "/hypr"
local hl_dir = hypr_dir .. "/hyprland"
local cconf_dir = config_dir .. "/caelestia"

-- Safely load a Lua table from a file
local function load_lua_table(path)
    if not path or path == "" then return nil end
    local f = io.open(path, "r")
    if not f then return nil end
    f:close()

    local chunk, err = loadfile(path)
    if not chunk then
        if io and io.stderr then
            io.stderr:write("Error loading Lua file " .. path .. ": " .. tostring(err) .. "\n")
        end
        return nil
    end

    local status, res = pcall(chunk)
    if not status then
        if io and io.stderr then
            io.stderr:write("Error executing Lua file " .. path .. ": " .. tostring(res) .. "\n")
        end
        return nil
    end

    if type(res) == "table" then
        return res
    end
    return nil
end

-- Recursively merge src table into dst
local function merge_tables(dst, src)
    if type(dst) ~= "table" or type(src) ~= "table" then return end
    for k, v in pairs(src) do
        if type(v) == "table" and type(dst[k]) == "table" then
            merge_tables(dst[k], v)
        else
            dst[k] = v
        end
    end
end

-- Load core window/layer/workspace rules
local rules = load_lua_table(hl_dir .. "/rules.lua") or {
    windowrules = {},
    layerrules = {},
    workspaces = {},
}

-- Load user override rules from ~/.config/caelestia/hypr-user.lua
local user_rules = load_lua_table(cconf_dir .. "/hypr-user.lua")
if user_rules then
    merge_tables(rules, user_rules)
end

-- If native Hyprland C/Lua API is present, register rules
local api = _G and (_G.hyprland or _G.hypr)
if api then
    if type(api.add_window_rule) == "function" and rules.windowrules then
        for _, rule in pairs(rules.windowrules) do
            api.add_window_rule(rule)
        end
    end
    if type(api.add_layer_rule) == "function" and rules.layerrules then
        for _, rule in pairs(rules.layerrules) do
            api.add_layer_rule(rule)
        end
    end
    if type(api.add_workspace_rule) == "function" and rules.workspaces then
        for _, rule in pairs(rules.workspaces) do
            api.add_workspace_rule(rule)
        end
    end
end

return rules
