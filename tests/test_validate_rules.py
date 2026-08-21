#!/usr/bin/env python3
"""
Version-aware unit tests for Hyprland window/layer/workspace rule validation.
Tests current named windowrule block syntax, declarative match syntax,
Lua configuration mode, user override file preservation, and version-aware parser checks.
"""

import sys
import unittest
import tempfile
from pathlib import Path

# Add hypr/scripts to python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hypr" / "scripts"))

from validate_rules import (
    validate_conf_file,
    validate_lua_file,
    validate_file,
    validate_with_installed_parser,
    check_regex_validity,
)


class TestRuleValidation(unittest.TestCase):

    def test_regex_validity(self):
        self.assertTrue(check_regex_validity("foot|equibop"))
        self.assertTrue(check_regex_validity(".*polkit.*"))
        self.assertFalse(check_regex_validity("[unclosed_bracket"))

    def test_named_windowrule_block_syntax(self):
        content = """
windowrule rule_opacity {
    match {
        fullscreen = false
    }
    opacity = $windowOpacity override
}

windowrule rule_float_utils {
    match {
        class = ^(foot|yad)$
    }
    float = true
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_conf_file(tmp_path, target_version="0.45.0")
        tmp_path.unlink()
        self.assertEqual(errors, [])

    def test_declarative_match_line_syntax(self):
        content = """
windowrule = opacity $windowOpacity override, match:fullscreen false
windowrule = float true, match:class foot
"""
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_conf_file(tmp_path, target_version="0.40.0")
        tmp_path.unlink()
        self.assertEqual(errors, [])

    def test_version_aware_deprecated_windowrulev2_warning(self):
        content = "windowrulev2 = opacity $windowOpacity override, fullscreen:0\n"
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        # Version >= 0.45 flags deprecated windowrulev2
        errors_v45 = validate_conf_file(tmp_path, target_version="0.45.0")
        tmp_path.unlink()
        self.assertTrue(any("windowrulev2" in err for err in errors_v45))

    def test_unclosed_block_brace(self):
        content = """
windowrule rule_unclosed {
    match {
        class = ^(foot)$
    # missing closing braces
"""
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_conf_file(tmp_path, target_version="0.45.0")
        tmp_path.unlink()
        self.assertTrue(len(errors) > 0)

    def test_invalid_regex_in_match_block(self):
        content = """
windowrule rule_bad_regex {
    match {
        class = ^([bad_regex)$
    }
    float = true
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_conf_file(tmp_path, target_version="0.45.0")
        tmp_path.unlink()
        self.assertTrue(any("Invalid regex" in err for err in errors))

    def test_lua_configuration_mode_validation(self):
        content = """
return {
    windowrules = {
        rule_float = {
            match = { class = "^(foot)$" },
            float = true,
        },
    },
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_lua_file(tmp_path)
        tmp_path.unlink()
        self.assertEqual(errors, [])

    def test_lua_configuration_unmatched_brace(self):
        content = "return { windowrules = { rule_float = { match = { class = 'foot' } "
        with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        errors = validate_lua_file(tmp_path)
        tmp_path.unlink()
        self.assertTrue(len(errors) > 0)

    def test_user_override_file_preservation(self):
        # Ensure validator does not write or mutate user override file
        override_content = "# User custom rules\nwindowrule my_rule {\n    match {\n        class = ^(my_app)$\n    }\n    float = true\n}\n"
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(override_content)
            tmp_path = Path(f.name)

        errors = validate_file(tmp_path, target_version="0.45.0")
        read_back = tmp_path.read_text()
        tmp_path.unlink()

        self.assertEqual(errors, [])
        self.assertEqual(read_back, override_content)

    def test_validate_core_repo_files(self):
        repo_root = Path(__file__).resolve().parent.parent
        rules_conf = repo_root / "hypr" / "hyprland" / "rules.conf"
        rules_lua = repo_root / "hypr" / "hyprland" / "rules.lua"

        self.assertTrue(rules_conf.exists())
        self.assertTrue(rules_lua.exists())

        errs_conf = validate_conf_file(rules_conf, target_version="0.45.0")
        errs_lua = validate_lua_file(rules_lua)

        self.assertEqual(errs_conf, [], f"rules.conf has errors: {errs_conf}")
        self.assertEqual(errs_lua, [], f"rules.lua has errors: {errs_lua}")


if __name__ == "__main__":
    unittest.main()
