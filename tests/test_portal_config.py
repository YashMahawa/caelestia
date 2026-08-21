#!/usr/bin/env python3
"""
Smoke test and validation suite for xdg-desktop-portal configuration and preflight script.
Verifies that:
1. Portal configuration files exist and are well-formed ([preferred] section).
2. Every mapped backend/interface is actually provided by an installed or standard portal descriptor.
3. Incorrect backends (e.g. gnome-keyring) and non-existent/unsupported portal interfaces (e.g. Clipboard) are detected and flagged.
4. Missing or malformed custom config files fall back to normal portal startup rather than skipping portal initialization.
"""

import os
import pathlib
import re
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).parent.parent.resolve()
SYSTEM_PORTAL_DIRS = [
    REPO_ROOT / "tests" / "fixtures" / "portals",
    pathlib.Path("/usr/share/xdg-desktop-portal/portals"),
    pathlib.Path("/usr/local/share/xdg-desktop-portal/portals"),
    pathlib.Path("/etc/xdg-desktop-portal/portals"),
    pathlib.Path.home() / ".local/share/xdg-desktop-portal/portals",
]

# Standard reference portal descriptors (used as fallbacks if system packages are not installed in test environment)
STANDARD_REFERENCE_PORTALS = {
    "hyprland": {
        "org.freedesktop.impl.portal.ScreenCast",
        "org.freedesktop.impl.portal.Screenshot",
        "org.freedesktop.impl.portal.GlobalShortcuts",
        "org.freedesktop.impl.portal.InputCapture",
    },
    "gtk": {
        "org.freedesktop.impl.portal.Account",
        "org.freedesktop.impl.portal.AppChooser",
        "org.freedesktop.impl.portal.DynamicLauncher",
        "org.freedesktop.impl.portal.FileChooser",
        "org.freedesktop.impl.portal.Inhibit",
        "org.freedesktop.impl.portal.Notification",
        "org.freedesktop.impl.portal.Print",
        "org.freedesktop.impl.portal.Settings",
        "org.freedesktop.impl.portal.Access",
        "org.freedesktop.impl.portal.Lockdown",
        "org.freedesktop.impl.portal.Email",
    },
}


def load_installed_portal_descriptors(extra_dirs=None):
    """
    Scans portal descriptor directories (*.portal) and builds a map:
    backend_name -> set(supported_interfaces)
    """
    portal_dirs = list(SYSTEM_PORTAL_DIRS)
    if extra_dirs:
        portal_dirs = [pathlib.Path(d) for d in extra_dirs] + portal_dirs

    backends = {}
    found_any = False

    for portal_dir in portal_dirs:
        if not portal_dir.exists():
            continue

        for descriptor_path in portal_dir.glob("*.portal"):
            found_any = True
            backend_name = descriptor_path.stem
            supported_interfaces = set()

            with open(descriptor_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Interfaces="):
                        ifaces = line.split("=", 1)[1].split(";")
                        for iface in ifaces:
                            iface = iface.strip()
                            if iface:
                                supported_interfaces.add(iface)

            backends[backend_name] = supported_interfaces

    if not found_any:
        # Fall back to standard reference descriptors
        return STANDARD_REFERENCE_PORTALS

    return backends


def validate_portal_config_content(content, available_backends):
    """
    Validates a portal config string against available backend descriptors.
    Returns a tuple (is_valid, list_of_errors).
    """
    errors = []
    lines = content.splitlines()

    has_preferred = False
    in_preferred = False

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section == "preferred":
                has_preferred = True
                in_preferred = True
            else:
                in_preferred = False
            continue

        if not in_preferred:
            continue

        if "=" not in line:
            errors.append(f"Line {line_num}: Invalid line format (missing '='): {line}")
            continue

        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()

        backend_list = [b.strip() for b in val.split(";") if b.strip()]

        if key == "default":
            for backend in backend_list:
                if backend not in available_backends:
                    errors.append(f"Line {line_num}: Unknown default backend '{backend}'")
            continue

        interface = key
        for backend in backend_list:
            if backend not in available_backends:
                errors.append(
                    f"Line {line_num}: Interface '{interface}' maps to unknown backend '{backend}' "
                    f"(no matching .portal descriptor)"
                )
            else:
                supported_interfaces = available_backends[backend]
                if interface not in supported_interfaces:
                    errors.append(
                        f"Line {line_num}: Backend '{backend}' does not provide interface '{interface}'"
                    )

    if not has_preferred:
        errors.append("Missing required '[preferred]' section header")

    return (len(errors) == 0, errors)


class TestPortalConfigAndPreflight(unittest.TestCase):
    def setUp(self):
        self.portal_configs = [
            REPO_ROOT / "xdg-desktop-portal" / "hyprland-portals.conf",
            REPO_ROOT / "xdg-desktop-portal" / "portals.conf",
        ]

    def test_repo_portal_configs_exist(self):
        for conf in self.portal_configs:
            self.assertTrue(conf.exists(), f"Portal config missing: {conf}")

    def test_repo_portal_configs_validation_against_descriptors(self):
        backends = load_installed_portal_descriptors()

        for conf in self.portal_configs:
            with open(conf, "r", encoding="utf-8") as f:
                content = f.read()

            is_valid, errors = validate_portal_config_content(content, backends)
            self.assertTrue(
                is_valid,
                f"Validation failed for {conf.name}:\n" + "\n".join(errors),
            )

    def test_rejects_invalid_backend_gnome_keyring(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.Secret=gnome-keyring;gtk;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("gnome-keyring" in err for err in errors),
            f"Expected gnome-keyring error, got: {errors}",
        )

    def test_rejects_unsupported_clipboard_interface(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.Clipboard=gtk;hyprland;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Clipboard" in err for err in errors),
            f"Expected Clipboard error, got: {errors}",
        )

    def test_rejects_unsupported_openuri_for_gtk(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.OpenURI=gtk;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("OpenURI" in err for err in errors),
            f"Expected OpenURI error, got: {errors}",
        )

    def test_rejects_unsupported_wallpaper_for_gtk(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.Wallpaper=gtk;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Wallpaper" in err for err in errors),
            f"Expected Wallpaper error, got: {errors}",
        )

    def test_rejects_unsupported_inhibit_for_hyprland(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.Inhibit=hyprland;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Inhibit" in err for err in errors),
            f"Expected Inhibit error, got: {errors}",
        )

    def test_rejects_unknown_backend_gnome(self):
        backends = load_installed_portal_descriptors()
        invalid_content = """[preferred]
default=gtk;hyprland;
org.freedesktop.impl.portal.Secret=gnome;
"""
        is_valid, errors = validate_portal_config_content(invalid_content, backends)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("gnome" in err for err in errors),
            f"Expected gnome error, got: {errors}",
        )

    def test_portal_script_preflight_missing_config_fallback(self):
        script_path = REPO_ROOT / "hypr" / "scripts" / "portal.sh"
        self.assertTrue(script_path.exists())

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a mock bin directory with a dummy systemctl script to avoid actual systemd invocation
            bin_dir = os.path.join(tmp_dir, "bin")
            os.makedirs(bin_dir, exist_ok=True)

            mock_systemctl = os.path.join(bin_dir, "systemctl")
            with open(mock_systemctl, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(mock_systemctl, 0o755)

            mock_dbus = os.path.join(bin_dir, "dbus-update-activation-environment")
            with open(mock_dbus, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(mock_dbus, 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["XDG_CONFIG_HOME"] = os.path.join(tmp_dir, "config")

            res = subprocess.run(
                [str(script_path)],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(res.returncode, 0, f"Script failed with stderr: {res.stderr}")
            self.assertIn("Notice:", res.stderr)
            self.assertNotIn("Skipping xdg-desktop-portal initialization", res.stderr)

    def test_portal_script_preflight_malformed_config_fallback(self):
        script_path = REPO_ROOT / "hypr" / "scripts" / "portal.sh"

        with tempfile.TemporaryDirectory() as tmp_dir:
            bin_dir = os.path.join(tmp_dir, "bin")
            os.makedirs(bin_dir, exist_ok=True)

            mock_systemctl = os.path.join(bin_dir, "systemctl")
            with open(mock_systemctl, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(mock_systemctl, 0o755)

            mock_dbus = os.path.join(bin_dir, "dbus-update-activation-environment")
            with open(mock_dbus, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(mock_dbus, 0o755)

            config_dir = os.path.join(tmp_dir, "config", "xdg-desktop-portal")
            os.makedirs(config_dir, exist_ok=True)
            malformed_file = os.path.join(config_dir, "hyprland-portals.conf")
            with open(malformed_file, "w") as f:
                f.write("invalid_content_without_preferred_section\n")

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["XDG_CONFIG_HOME"] = os.path.join(tmp_dir, "config")

            res = subprocess.run(
                [str(script_path)],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(res.returncode, 0, f"Script failed with stderr: {res.stderr}")
            self.assertIn("Warning:", res.stderr)
            self.assertIn("malformed", res.stderr)


if __name__ == "__main__":
    unittest.main()
