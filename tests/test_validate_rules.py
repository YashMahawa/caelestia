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
    strip_ansi,
    is_debug_or_log_line,
    is_recognized_parser_diagnostic,
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

    def test_validate_with_installed_parser_unknown_option_fallback(self):
        from unittest.mock import patch, MagicMock
        with patch("shutil.which", return_value="/usr/bin/hyprland"):
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = ""
            mock_res.stderr = "[ERROR] Unknown option: --config-only\n"
            with patch("subprocess.run", return_value=mock_res):
                with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
                    f.write("windowrule rule_test {\n    match {\n        class = ^(test)$\n    }\n}\n")
                    tmp_path = Path(f.name)
                result = validate_with_installed_parser(tmp_path)
                tmp_path.unlink()
                self.assertIsNone(result)

    def test_validate_with_installed_parser_supported_option_success(self):
        from unittest.mock import patch, MagicMock
        with patch("shutil.which", return_value="/usr/bin/hyprland"):
            mock_help = MagicMock()
            mock_help.stdout = "Usage: hyprland [--verify-config] [-c CONFIG]\n"
            mock_help.stderr = ""
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Config verified successfully\n"
            mock_res.stderr = ""
            def mock_run(cmd, **kwargs):
                if "--help" in cmd:
                    return mock_help
                return mock_res
            with patch("subprocess.run", side_effect=mock_run):
                with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
                    f.write("windowrule rule_test {\n    match {\n        class = ^(test)$\n    }\n}\n")
                    tmp_path = Path(f.name)
                result = validate_with_installed_parser(tmp_path)
                tmp_path.unlink()
                self.assertEqual(result, [])

    def test_strip_ansi_and_log_filtering(self):
        ansi_text = "\x1b[31m[ERROR] Config error at line 5\x1b[0m"
        self.assertEqual(strip_ansi(ansi_text), "[ERROR] Config error at line 5")

        debug_line = "[DEBUG] Config: loading file /tmp/test.conf"
        self.assertTrue(is_debug_or_log_line(debug_line))
        self.assertFalse(is_recognized_parser_diagnostic(debug_line))

        error_line = "Config error: syntax error at line 2"
        self.assertFalse(is_debug_or_log_line(error_line))
        self.assertTrue(is_recognized_parser_diagnostic(error_line))

    def test_validate_with_installed_parser_debug_output_returns_none(self):
        from unittest.mock import patch, MagicMock
        with patch("shutil.which", return_value="/usr/bin/hyprland"):
            mock_help = MagicMock()
            mock_help.stdout = "Usage: hyprland [--verify-config] [-c CONFIG]\n"
            mock_help.stderr = ""
            mock_res = MagicMock()
            mock_res.returncode = 1
            # 11 DEBUG lines like in the reported test failure
            debug_lines = "\n".join([
                "DEBUG: Loading config file /tmp/tmp123.conf",
                "[DEBUG] Setting config option windowrule",
                "[DEBUG] Error handling initialized",
                "[DEBUG] Config parsing stage 1",
                "[DEBUG] Config parsing stage 2",
                "[DEBUG] Config option windowrule parsed",
                "[DEBUG] Invalid backend handle",
                "[DEBUG] Error in display initialization",
                "[DEBUG] Config file processed",
                "[DEBUG] Exiting with code 1",
                "[DEBUG] Cleaning up resources"
            ])
            mock_res.stdout = ""
            mock_res.stderr = debug_lines
            def mock_run(cmd, **kwargs):
                if "--help" in cmd:
                    return mock_help
                return mock_res
            with patch("subprocess.run", side_effect=mock_run):
                with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
                    f.write("windowrule rule_test {\n    match {\n        class = ^(test)$\n    }\n}\n")
                    tmp_path = Path(f.name)
                # Should return None (fallback to internal structural validator) rather than returning DEBUG lines as errors
                result = validate_with_installed_parser(tmp_path)
                tmp_path.unlink()
                self.assertIsNone(result)

    def test_validate_with_installed_parser_supported_option_failure(self):
        from unittest.mock import patch, MagicMock
        with patch("shutil.which", return_value="/usr/bin/hyprland"):
            mock_help = MagicMock()
            mock_help.stdout = "Usage: hyprland [--verify-config] [-c CONFIG]\n"
            mock_help.stderr = ""
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = ""
            mock_res.stderr = "\x1b[31m[ERROR] Config error: syntax error at line 2\x1b[0m\n"
            def mock_run(cmd, **kwargs):
                if "--help" in cmd:
                    return mock_help
                return mock_res
            with patch("subprocess.run", side_effect=mock_run):
                with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
                    f.write("invalid config content\n")
                    tmp_path = Path(f.name)
                result = validate_with_installed_parser(tmp_path)
                tmp_path.unlink()
                self.assertIsNotNone(result)
                self.assertTrue(len(result) > 0)
                self.assertTrue(any("syntax error" in err for err in result))


if __name__ == "__main__":
    unittest.main()
