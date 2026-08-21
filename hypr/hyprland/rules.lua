-- Hyprland rules (Lua mode) for Caelestia
return {
    windowrules = {
        rule_opacity = {
            match = { fullscreen = false },
            opacity = "$windowOpacity override",
        },
        rule_opaque_apps = {
            match = { class = "^(foot|equibop|org\\.quickshell|imv|swappy)$" },
            opaque = true,
        },
        rule_center_floating = {
            match = { floating = true, xwayland = false },
            center = true,
        },
        rule_float_utilities = {
            match = { class = "^(guifetch|yad|zenity|wev|org\\.gnome\\.FileRoller|file-roller|blueman-manager|com\\.github\\.GradienceTeam\\.Gradience|feh|imv|system-config-printer|org\\.quickshell)$" },
            float = true,
        },
        rule_auth_prompts = {
            match = { class = "^(.*polkit.*|.*policykit.*|pinentry.*|gcr-prompter|org\\.gnome\\.keyring\\.SystemPrompter)$" },
            float = true,
            center = true,
        },
        rule_auth_titles = {
            match = { title = "^(Authentication Required|Unlock Keyring|PolicyKit1 Daemon)$" },
            float = true,
            center = true,
        },
        rule_net_controls = {
            match = { class = "^(nm-connection-editor|nm-applet|blueman-manager|blueman-services|blueman-sendto|wihotspot-gui)$" },
            float = true,
            center = true,
        },
        rule_nmtui = {
            match = { class = "^(foot)$", title = "^(nmtui)$" },
            float = true,
            size = "60% 70%",
            center = true,
        },
        rule_gnome_settings = {
            match = { class = "^(org\\.gnome\\.Settings)$" },
            float = true,
            size = "70% 80%",
            center = true,
        },
        rule_audio_popups = {
            match = { class = "^(org\\.pulseaudio\\.pavucontrol|pavucontrol|pwvucontrol|helvum|easyeffects|qpwgraph|yad-icon-browser)$" },
            float = true,
            size = "60% 70%",
            center = true,
        },
        rule_nwg_look = {
            match = { class = "^(nwg-look)$" },
            float = true,
            size = "50% 60%",
            center = true,
        },
        rule_special_sysmon = {
            match = { class = "^(btop)$" },
            workspace = "special:sysmon",
        },
        rule_special_music = {
            match = { class = "^(feishin|Spotify|Supersonic|Cider|com\\.github\\.th-ch\\.youtube-music|Plexamp|com-maxrave-simpmusic-MainKt)$" },
            workspace = "special:music",
        },
        rule_special_music_spotify = {
            match = { initialTitle = "^(Spotify|Spotify Free)$" },
            workspace = "special:music",
        },
        rule_special_communication = {
            match = { class = "^(discord|equibop|vesktop|whatsapp)$" },
            workspace = "special:communication",
        },
        rule_special_todo = {
            match = { class = "^(Todoist)$" },
            workspace = "special:todo",
        },
        rule_desktop_portals = {
            match = { class = "^(org\\.freedesktop\\.impl\\.portal\\.desktop\\..*)$" },
            float = true,
            center = true,
            size = "70% 70%",
        },
        rule_dialog_pickers = {
            match = { title = "^(Select|Open|Save)( a)? (File|Folder|Directory)(s)?$" },
            float = true,
            center = true,
        },
        rule_file_operations = {
            match = { title = "^(File|Folder) (Operation|Upload|Properties)( Progress)?$" },
            float = true,
        },
        rule_dialog_properties = {
            match = { title = "^(.* Properties)$" },
            float = true,
        },
        rule_export_png = {
            match = { title = "^(Export Image as PNG)$" },
            float = true,
        },
        rule_gimp_crash = {
            match = { title = "^(GIMP Crash Debug)$" },
            float = true,
        },
        rule_save_as = {
            match = { title = "^(Save As)$" },
            float = true,
        },
        rule_library = {
            match = { title = "^(Library)$" },
            float = true,
        },
        rule_creative_opaque = {
            match = { class = "^(krita|gimp|inkscape|darktable|resolve|kdenlive|shotcut|blender|godot)$" },
            opaque = true,
        },
        rule_ueberzugpp = {
            match = { class = "^(ueberzugpp_.*)$" },
            float = true,
            noinitialfocus = true,
        },
        rule_steam_rounding = {
            match = { class = "^(steam)$" },
            rounding = 10,
        },
        rule_steam_friends = {
            match = { class = "^(steam)$", title = "^(Friends List)$" },
            float = true,
        },
        rule_games = {
            match = { class = "^(steam_app_(default|[0-9]+)|gamescope)$" },
            opaque = true,
            immediate = true,
            idleinhibit = "always",
        },
        rule_atlauncher = {
            match = { class = "^(com-atlauncher-App)$", title = "^(ATLauncher Console)$" },
            float = true,
        },
        rule_pandora = {
            match = { class = "^(PandoraLauncher)$", title = "^(Minecraft Game Output)$" },
            float = true,
        },
        rule_fusion360 = {
            match = { class = "^(fusion360\\.exe)$", title = "^(Fusion360|(Marking Menu))$" },
            noblur = true,
        },
        rule_xwayland_popups = {
            match = { xwayland = true, title = "^(win[0-9]+)$" },
            nodim = true,
            noshadow = true,
            rounding = 10,
        },
    },
    layerrules = {
        rule_picker_anim = { match = { namespace = "^(hyprpicker)$" }, animation = "fade" },
        rule_logout_dialog = { match = { namespace = "^(logout_dialog)$" }, animation = "fade" },
        rule_selection = { match = { namespace = "^(selection)$" }, animation = "fade" },
        rule_wayfreeze = { match = { namespace = "^(wayfreeze)$" }, animation = "fade" },
        rule_fuzzel = { match = { namespace = "^(launcher)$" }, animation = "popin 80%", blur = true },
        rule_shell_noanim = { match = { namespace = "^(caelestia-(border-exclusion|area-picker)|caelestia-immersive-lyrics)$" }, noanim = true },
        rule_shell_drawers_anim = { match = { namespace = "^(caelestia-(drawers|background))$" }, animation = "fade" },
        rule_shell_drawers = { match = { namespace = "^(caelestia-drawers)$" }, blur = true, ignorealpha = 0.82 },
        rule_shell_bg = { match = { namespace = "^(caelestia-background)$" }, blur = true, ignorealpha = 0.25 },
    },
    workspaces = {
        rule_gaps_single = { match = { workspace = "w[tv1]s[false]" }, gapsout = "$singleWindowGapsOut" },
        rule_gaps_fullscreen = { match = { workspace = "f[1]s[false]" }, gapsout = "$singleWindowGapsOut" },
    },
}
