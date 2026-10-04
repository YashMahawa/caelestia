-- Native Hyprland Lua entry point for the existing Caelestia configuration.
-- The .conf files below are treated only as Caelestia-owned data; Hyprland's
-- deprecated hyprlang parser is never invoked.

local home = os.getenv("HOME") or "/home/yash"
local hypr = home .. "/.config/hypr"
local caelestia = home .. "/.config/caelestia"

local function trim(value)
    return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function strip_comment(line)
    local quote, escaped = nil, false
    for index = 1, #line do
        local char = line:sub(index, index)
        if escaped then
            escaped = false
        elseif char == "\\" then
            escaped = true
        elseif quote then
            if char == quote then quote = nil end
        elseif char == "'" or char == '"' then
            quote = char
        elseif char == "#" and (index == 1 or line:sub(index - 1, index - 1):match("%s")) then
            return trim(line:sub(1, index - 1))
        end
    end
    return trim(line)
end

local vars = {}

local function expand_once(value)
    return (value:gsub("%$([%w_]+)", function(name)
        for length = #name, 1, -1 do
            local prefix = name:sub(1, length)
            local replacement = vars[prefix] or os.getenv(prefix)
            if replacement ~= nil then
                return tostring(replacement) .. name:sub(length + 1)
            end
        end
        return "$" .. name
    end))
end

local function expand(value)
    local previous = value
    for _ = 1, 12 do
        local next_value = expand_once(previous)
        if next_value == previous then return next_value end
        previous = next_value
    end
    return previous
end

local function read_lines(path)
    local lines = {}
    local file = io.open(path, "r")
    if not file then return lines end
    for line in file:lines() do table.insert(lines, line) end
    file:close()
    return lines
end

local function load_variables(path)
    for _, raw in ipairs(read_lines(path)) do
        local line = strip_comment(raw)
        local name, value = line:match("^%$([%w_]+)%s*=%s*(.-)%s*$")
        if name then vars[name] = expand(value) end
    end
end

load_variables(hypr .. "/scheme/current.conf")
load_variables(hypr .. "/variables.conf")

local function scalar(value)
    value = trim(expand(value))
    if value == "true" then return true end
    if value == "false" then return false end
    local number = tonumber(value)
    if number ~= nil then return number end
    return value
end

local function set_path(root, dotted_key, value)
    local cursor = root
    local parts = {}
    for part in dotted_key:gmatch("[^%.]+") do table.insert(parts, part) end
    for index = 1, #parts - 1 do
        local part = parts[index]
        if type(cursor[part]) ~= "table" then cursor[part] = {} end
        cursor = cursor[part]
    end
    cursor[parts[#parts]] = value
end

local function merge(destination, source)
    for key, value in pairs(source) do
        if type(value) == "table" and type(destination[key]) == "table" then
            merge(destination[key], value)
        else
            destination[key] = value
        end
    end
end

local function split_commas(value)
    local result, current, quote, escaped = {}, {}, nil, false
    for index = 1, #value do
        local char = value:sub(index, index)
        if escaped then
            table.insert(current, char)
            escaped = false
        elseif char == "\\" then
            table.insert(current, char)
            escaped = true
        elseif quote then
            table.insert(current, char)
            if char == quote then quote = nil end
        elseif char == "'" or char == '"' then
            table.insert(current, char)
            quote = char
        elseif char == "," then
            table.insert(result, trim(table.concat(current)))
            current = {}
        else
            table.insert(current, char)
        end
    end
    table.insert(result, trim(table.concat(current)))
    return result
end

local config = {}
local devices, monitors, curves, animations = {}, {}, {}, {}
local exec_once, exec_reload = {}, {}
-- Keep strong references to native keybind objects for the lifetime of the
-- compositor configuration. This also makes their actual runtime state
-- inspectable through `hyprctl repl`.
_G.caelestia_keybinds = {}

local function parse_config_file(path)
    local local_root, stack = {}, {}
    local current = local_root
    for _, raw in ipairs(read_lines(path)) do
        local line = strip_comment(raw)
        if line ~= "" and not line:match("^%$[%w_]+%s*=") then
            local section = line:match("^([%w_%.%-]+)%s*{%s*$")
            if section then
                local child = {}
                current[section] = child
                table.insert(stack, current)
                current = child
            elseif line == "}" then
                current = table.remove(stack) or local_root
            else
                local key, value = line:match("^([%w_%.%-]+)%s*=%s*(.-)%s*$")
                if key then
                    value = expand(value)
                    if key == "exec-once" then
                        table.insert(exec_once, value)
                    elseif key == "exec" then
                        table.insert(exec_reload, value)
                    elseif key == "env" then
                        local name, env_value = value:match("^%s*([^,]+),%s*(.*)$")
                        if name then hl.env(trim(name), trim(env_value)) end
                    elseif key == "monitor" then
                        local fields = split_commas(value)
                        table.insert(monitors, {
                            output = fields[1] or "",
                            mode = fields[2] or "preferred",
                            position = fields[3] or "auto",
                            scale = fields[4] or "auto",
                            cm = fields[6],
                        })
                    elseif key == "bezier" then
                        local fields = split_commas(value)
                        table.insert(curves, {
                            name = fields[1],
                            points = {{tonumber(fields[2]), tonumber(fields[3])}, {tonumber(fields[4]), tonumber(fields[5])}},
                        })
                    elseif key == "animation" then
                        local fields = split_commas(value)
                        table.insert(animations, {
                            leaf = fields[1], enabled = scalar(fields[2]), speed = tonumber(fields[3]),
                            bezier = fields[4], style = fields[5],
                        })
                    else
                        set_path(current, key, scalar(value))
                    end
                end
            end
        end
    end

    if local_root.device then
        table.insert(devices, local_root.device)
        local_root.device = nil
    end
    merge(config, local_root)
end

local config_files = {
    hypr .. "/hyprland/env.conf",
    hypr .. "/hyprland/general.conf",
    hypr .. "/hyprland/input.conf",
    hypr .. "/hyprland/misc.conf",
    hypr .. "/hyprland/animations.conf",
    hypr .. "/hyprland/decoration.conf",
    hypr .. "/hyprland/group.conf",
    hypr .. "/hyprland/execs.conf",
    hypr .. "/hyprland/gestures.conf",
    caelestia .. "/hypr-user.conf",
    hypr .. "/monitors.conf",
    hypr .. "/caelestia-display.conf",
    hypr .. "/caelestia-monitors-runtime.conf",
}

-- Match the original fallback monitor rule before output-specific rules.
table.insert(monitors, { output = "", mode = "preferred", position = "auto", scale = "1" })
for _, path in ipairs(config_files) do parse_config_file(path) end

-- A compositor restarted by start-hyprland's safe-mode watchdog begins with
-- Hyprland's generated Lua configuration. Explicitly clear its marker so the
-- warning and generated defaults cannot remain authoritative after reload.
config.autogenerated = 0

-- Repeated directives are represented by dedicated Lua APIs, not config keys.
if config.animations then
    config.animations.bezier = nil
    config.animations.animation = nil
end
config.gesture = nil
config.windowrule = nil
config.layerrule = nil
config.workspace = nil

hl.config(config)

for _, device in ipairs(devices) do hl.device(device) end
for _, monitor in ipairs(monitors) do
    local rule = {
        output = monitor.output,
        mode = monitor.mode,
        position = monitor.position,
        scale = monitor.scale,
    }
    if monitor.cm and monitor.cm ~= "" then rule.cm = monitor.cm end
    hl.monitor(rule)
end
for _, curve in ipairs(curves) do
    hl.curve(curve.name, { type = "bezier", points = curve.points })
end
for _, animation in ipairs(animations) do
    local rule = {
        leaf = animation.leaf,
        enabled = animation.enabled == true or animation.enabled == 1,
        speed = animation.speed,
        bezier = animation.bezier,
    }
    if animation.style and animation.style ~= "" then rule.style = animation.style end
    hl.animation(rule)
end

local function dispatch(command)
    hl.dispatch(hl.dsp.exec_cmd(command))
end

hl.on("hyprland.start", function()
    for _, command in ipairs(exec_once) do dispatch(command) end
end)

hl.on("config.reloaded", function()
    for _, command in ipairs(exec_reload) do dispatch(command) end
end)

local function parse_rules(path)
    local window_index, layer_index = 0, 0
    local boolean_effects = {
        float=true, tile=true, fullscreen=true, maximize=true, center=true,
        pseudo=true, no_initial_focus=true, pin=true, persistent_size=true,
        allows_input=true, dim_around=true, decorate=true, focus_on_activate=true,
        keep_aspect_ratio=true, nearest_neighbor=true, no_anim=true, no_blur=true,
        no_dim=true, no_focus=true, no_follow_mouse=true, no_max_size=true,
        no_shadow=true, no_shortcuts_inhibit=true, opaque=true, force_rgbx=true,
        sync_fullscreen=true, immediate=true, xray=true, render_unfocused=true,
        no_screen_share=true, no_vrr=true, no_auto_hdr=true, stay_focused=true,
        confine_pointer=true,
    }
    for _, raw in ipairs(read_lines(path)) do
        local line = strip_comment(raw)
        local kind, body = line:match("^(windowrule)%s*=%s*(.+)$")
        if not kind then kind, body = line:match("^(layerrule)%s*=%s*(.+)$") end
        if not kind then kind, body = line:match("^(workspace)%s*=%s*(.+)$") end
        if body then
            body = expand(body)
            local fields = split_commas(body)
            if kind == "windowrule" then
                window_index = window_index + 1
                local effect_key, effect_value = fields[1]:match("^(%S+)%s*(.-)%s*$")
                local rule = { name = "caelestia-migrated-window-" .. window_index, match = {} }
                for index = 2, #fields do
                    local match_key, match_value = fields[index]:match("^match:([%w_]+)%s+(.+)$")
                    if match_key then
                        if match_value == "true" or match_value == "1" then match_value = true
                        elseif match_value == "false" or match_value == "0" then match_value = false end
                        rule.match[match_key] = match_value
                    end
                end
                if boolean_effects[effect_key] then
                    rule[effect_key] = effect_value == "true" or effect_value == "1"
                elseif effect_key == "rounding" or effect_key == "border_size" then
                    rule[effect_key] = tonumber(effect_value)
                elseif effect_key == "size" or effect_key == "min_size" or effect_key == "max_size" then
                    -- Legacy "W% H%" sizes become monitor expressions; the
                    -- 0.56 rule engine silently ignores percentages.
                    rule[effect_key] = effect_value:gsub("(%d+%.?%d*)%%", function(pct)
                        return string.format("%g", tonumber(pct) / 100)
                    end):gsub("^(%S+)%s+(%S+)$", function(w, h)
                        local function axis(v, dim)
                            if v:match("^%d*%.?%d+$") and tonumber(v) <= 1 then return dim .. "*" .. v end
                            return v
                        end
                        return axis(w, "monitor_w") .. " " .. axis(h, "monitor_h")
                    end)
                else
                    rule[effect_key] = effect_value
                end
                hl.window_rule(rule)
            elseif kind == "layerrule" then
                layer_index = layer_index + 1
                local effect_key, effect_value = fields[1]:match("^(%S+)%s*(.-)%s*$")
                local rule = { name = "caelestia-migrated-layer-" .. layer_index, match = {} }
                for index = 2, #fields do
                    local match_key, match_value = fields[index]:match("^match:([%w_]+)%s+(.+)$")
                    if match_key then rule.match[match_key] = match_value end
                end
                if effect_key == "blur" or effect_key == "blur_popups" or effect_key == "no_anim" then
                    rule[effect_key] = effect_value == "true" or effect_value == "1"
                elseif effect_key == "ignore_alpha" then
                    rule[effect_key] = tonumber(effect_value)
                else
                    rule[effect_key] = effect_value
                end
                hl.layer_rule(rule)
            elseif kind == "workspace" then
                local rule = { workspace = fields[1] }
                for index = 2, #fields do
                    local key, value = fields[index]:match("^([%w_]+):(.+)$")
                    if key then
                        if key == "gapsin" then key = "gaps_in" end
                        if key == "gapsout" then key = "gaps_out" end
                        rule[key] = scalar(value)
                    end
                end
                hl.workspace_rule(rule)
            end
        end
    end
end

parse_rules(hypr .. "/hyprland/rules.conf")
parse_rules(caelestia .. "/hypr-user.conf")

local dispatchers = {
    exec=true, workspace=true, movetoworkspace=true, togglegroup=true,
    moveoutofgroup=true, lockactivegroup=true, movefocus=true, movewindow=true,
    resizeactive=true, resizewindow=true, centerwindow=true, pin=true, fullscreen=true,
    killactive=true, submap=true,
}

local directions = { l = "left", r = "right", u = "up", d = "down" }

local function resize_handler(args)
    local exact, x, y = args:match("^(exact)%s+([^%s]+)%s+([^%s]+)$")
    if not exact then x, y = args:match("^([^%s]+)%s+([^%s]+)$") end
    if not x or not y then return hl.dsp.no_op() end
    local function pixels(value)
        local number = tonumber((value:gsub("%%$", ""))) or 0
        -- Native Lua resizing uses pixels. Preserve the useful feel of the old
        -- 10% binds with a stable 10 px per percentage-point conversion.
        if value:sub(-1) == "%" then number = number * 10 end
        return math.floor(number)
    end
    return hl.dsp.window.resize({
        x = pixels(x),
        y = pixels(y),
        relative = exact == nil,
    })
end

local function native_dispatcher(dispatcher, args, options)
    args = trim(args)
    if dispatcher == "workspace" then
        return hl.dsp.focus({ workspace = args })
    elseif dispatcher == "movetoworkspace" then
        return hl.dsp.window.move({ workspace = args })
    elseif dispatcher == "togglegroup" then
        return hl.dsp.group.toggle()
    elseif dispatcher == "moveoutofgroup" then
        return hl.dsp.window.move({ out_of_group = true })
    elseif dispatcher == "lockactivegroup" then
        return hl.dsp.group.lock_active(args ~= "" and args or "toggle")
    elseif dispatcher == "movefocus" then
        return hl.dsp.focus({ direction = directions[args] or args })
    elseif dispatcher == "movewindow" then
        if options.mouse then return hl.dsp.window.drag() end
        return hl.dsp.window.move({ direction = directions[args] or args })
    elseif dispatcher == "resizeactive" or dispatcher == "resizewindow" then
        if options.mouse then return hl.dsp.window.resize() end
        return resize_handler(args)
    elseif dispatcher == "centerwindow" then
        return hl.dsp.window.center()
    elseif dispatcher == "pin" then
        return hl.dsp.window.pin()
    elseif dispatcher == "fullscreen" then
        return hl.dsp.window.fullscreen({
            action = "toggle",
            mode = args:match("^1") and "maximized" or "fullscreen",
        })
    elseif dispatcher == "killactive" then
        return hl.dsp.window.close()
    elseif dispatcher == "submap" then
        return hl.dsp.submap(args)
    end
    return hl.dsp.no_op()
end

local function bind_options(kind)
    return {
        repeating = kind:find("e", 5, true) ~= nil,
        locked = kind:find("l", 5, true) ~= nil,
        release = kind:find("r", 5, true) ~= nil,
        mouse = kind:find("m", 5, true) ~= nil,
        ignore_mods = kind:find("i", 5, true) ~= nil,
        non_consuming = kind:find("n", 5, true) ~= nil,
        -- Keep desktop shortcuts available while an application uses the
        -- Wayland input-capture protocol (for example ChatGPT computer use).
        -- Without this, the binds remain visible in `hyprctl binds` but are
        -- silently withheld until the capture session ends.
        allow_input_capture = true,
        -- Fullscreen applications can separately request compositor shortcut
        -- inhibition. These are desktop-level bindings and must remain usable
        -- even while such a window (including ChatGPT) has keyboard focus.
        dont_inhibit = true,
    }
end

local function parse_binds(path)
    local active_submap = nil
    local parsed = {}
    for _, raw in ipairs(read_lines(path)) do
        local line = strip_comment(raw)
        local kind, body = line:match("^(bind[%a]*)%s*=%s*(.+)$")
        if kind and body then
            body = expand(body)
            local fields = split_commas(body)
            local dispatcher_index
            for index, field in ipairs(fields) do
                if dispatchers[field] then dispatcher_index = index break end
            end
            if dispatcher_index and dispatcher_index >= 3 then
                local modifiers = trim(fields[1] or "")
                local key = trim(fields[2] or "")
                if dispatcher_index > 3 then
                    key = trim(fields[dispatcher_index - 1])
                    modifiers = table.concat(fields, " + ", 1, dispatcher_index - 2)
                end
                local dispatcher = fields[dispatcher_index]
                local args = table.concat(fields, ",", dispatcher_index + 1)
                local keys = key
                if modifiers ~= "" then
                    modifiers = modifiers
                        :gsub("Super", "SUPER")
                        :gsub("Ctrl", "CTRL")
                        :gsub("Alt", "ALT")
                        :gsub("Shift", "SHIFT")
                        :gsub("%+", " + ")
                    keys = modifiers .. " + " .. key
                end
                local handler
                local options = bind_options(kind)
                if dispatcher == "exec" then
                    handler = hl.dsp.exec_cmd(args)
                else
                    handler = native_dispatcher(dispatcher, args, options)
                end
                if key == "catchall" then
                    keys = "catchall"
                    local guarded_handler = handler
                    handler = function()
                        if hl.is_key_down("Super_L") then hl.dispatch(guarded_handler) end
                    end
                end
                table.insert(parsed, { keys = keys, handler = handler, options = options })
            end
        end
    end

    -- Register each shortcut exactly once in Hyprland's native default map.
    -- The former custom `global` map plus a mirrored default-map copy caused
    -- both callbacks to run for every keypress: toggles immediately undid
    -- themselves and media actions advanced twice.
    for _, binding in ipairs(parsed) do
        -- `catchall` is only valid inside a named submap. It was used solely
        -- to interrupt the hold-to-open launcher and must not abort loading
        -- the entire default-map binding set.
        if binding.keys ~= "catchall" then
            table.insert(_G.caelestia_keybinds,
                hl.bind(binding.keys, binding.handler, binding.options))
        end
    end
end

parse_binds(hypr .. "/hyprland/keybinds.conf")

-- Display controls for keyboards without brightness keys. These native binds
-- consume the chords before clients see them, continue to work while input is
-- captured or shortcuts are inhibited, and require no watcher process.
local display_bind_options = {
    repeating = true,
    locked = true,
    non_consuming = false,
    allow_input_capture = true,
    dont_inhibit = true,
}

table.insert(_G.caelestia_keybinds,
    hl.bind("CTRL + up", hl.dsp.global("caelestia:brightnessSmallUp"), display_bind_options))
table.insert(_G.caelestia_keybinds,
    hl.bind("CTRL + down", hl.dsp.global("caelestia:brightnessSmallDown"), display_bind_options))
table.insert(_G.caelestia_keybinds,
    hl.bind("ALT + up", hl.dsp.global("caelestia:contrastUp"), display_bind_options))
table.insert(_G.caelestia_keybinds,
    hl.bind("ALT + down", hl.dsp.global("caelestia:contrastDown"), display_bind_options))

-- Native gesture equivalents for the current Caelestia gestures.
hl.gesture({ fingers = tonumber(vars.workspaceSwipeFingers), direction = "horizontal", action = "workspace" })
hl.gesture({ fingers = tonumber(vars.gestureFingers), direction = "up", action = {
    finish = function() dispatch(home .. "/.local/bin/caelestia-star-workspace toggle") end,
} })
hl.gesture({ fingers = tonumber(vars.gestureFingers), direction = "down", action = {
    finish = function() dispatch(home .. "/.local/bin/caelestia-star-workspace toggle") end,
} })
hl.gesture({ fingers = tonumber(vars.gestureFingersMore), direction = "down", action = {
    finish = function() dispatch(home .. "/.local/bin/caelestia-safe-suspend") end,
} })
