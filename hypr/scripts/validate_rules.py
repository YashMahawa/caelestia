#!/usr/bin/env python3
"""
Hyprland Window & Layer Rule Validator

Validates Hyprland window rules, layer rules, and workspace rules across:
1. Hyprland named block syntax (`windowrule <name> { match { ... } ... }`)
2. Declarative match syntax (`windowrule = ..., match:...`)
3. Native Lua configuration mode (`rules.lua` / `hypr-user.lua`)

Uses the actual installed Hyprland C++ parser when available on the system (`hyprland`),
falling back to version-aware structural parsing when running in headless or test environments.
Preserves all user override files without modification.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_regex_validity(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def get_hyprland_installed_version(hyprland_bin: str = "hyprland") -> str | None:
    bin_path = shutil.which(hyprland_bin) or shutil.which("Hyprland") or shutil.which("hyprland")
    if not bin_path:
        return None
    try:
        res = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout:
            # Match version numbers like v0.42.0 or 0.45.0
            m = re.search(r"v?(\d+\.\d+\.\d+)", res.stdout)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def strip_ansi(text: str) -> str:
    """Removes ANSI escape sequences from a string."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def is_debug_or_log_line(line: str) -> bool:
    """Checks if a line is debug or normal startup/logging output from Hyprland."""
    clean = line.strip()
    if not clean:
        return True

    upper = clean.upper()
    if upper.startswith(("[DEBUG]", "DEBUG:", "DEBUG ", "[LOG]", "LOG:", "LOG ", "[INFO]", "INFO:", "INFO ", "[TRACE]", "TRACE:", "TRACE ", "[WARN]", "WARN:", "WARN ")):
        return True
    if re.match(r'^\[?(DEBUG|LOG|INFO|TRACE|WARN)\]?:?\s', clean, re.IGNORECASE):
        return True
    return False


def is_recognized_parser_diagnostic(line: str) -> bool:
    """
    Checks if a line represents a recognized Hyprland config/parser diagnostic error.
    Ignores debug output, startup logs, and environment/display connection errors.
    """
    clean = line.strip()
    if is_debug_or_log_line(clean):
        return False

    patterns = [
        r'\bconfig error\b',
        r'\bsyntax error\b',
        r'\bparse error\b',
        r'\binvalid keyword\b',
        r'\binvalid directive\b',
        r'\binvalid rule\b',
        r'\bunknown keyword\b',
        r'\bunknown directive\b',
        r'\berror at line\b',
        r'\berror in\b',
        r'\bline \d+:',
        r'^\[?error\]?:?\s*(config|syntax|line|invalid|unknown|parse)',
    ]
    for pat in patterns:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def validate_with_installed_parser(file_path: Path, hyprland_bin: str | None = None) -> list[str] | None:
    bin_name = hyprland_bin or "hyprland"
    bin_path = shutil.which(bin_name) or shutil.which("Hyprland") or shutil.which("hyprland")
    if not bin_path:
        return None

    # Hyprland installed parser dry run / config validation
    try:
        # Create a temporary config that includes the target rule file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp:
            tmp.write(f"source = {file_path.resolve()}\n")
            tmp_path = tmp.name

        # Probe for supported non-destructive CLI validation options in the installed Hyprland
        help_output = ""
        try:
            help_res = subprocess.run([bin_path, "--help"], capture_output=True, text=True, timeout=5)
            help_output = strip_ansi(help_res.stdout + "\n" + help_res.stderr).lower()
        except Exception:
            pass

        # If --help failed or returned empty, do not run hyprland (prevents launching a compositor instance)
        if not help_output:
            os.unlink(tmp_path)
            return None

        # Build candidate commands ONLY using flags explicitly supported in --help
        candidate_cmds = []
        if "--verify-config" in help_output:
            candidate_cmds.append([bin_path, "--verify-config", "-c", tmp_path])
        if "--config-only" in help_output:
            candidate_cmds.append([bin_path, "-c", tmp_path, "--config-only"])
        if "--dry-run" in help_output:
            candidate_cmds.append([bin_path, "--dry-run", "-c", tmp_path])

        if not candidate_cmds:
            # None of the non-destructive validation flags are supported by this Hyprland binary
            os.unlink(tmp_path)
            return None

        env = os.environ.copy()
        env["HYPRLAND_NO_SD_NOTIFY"] = "1"

        res = None
        for cmd in candidate_cmds:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
                output = strip_ansi(proc.stderr + "\n" + proc.stdout).lower()

                # If the binary rejected the option as unknown/invalid, do not treat it as validation
                if any(kw in output for kw in ["unknown option", "invalid option", "unrecognized option", "unknown flag", "usage:"]):
                    continue

                res = proc
                break
            except Exception:
                continue

        os.unlink(tmp_path)

        if res is None:
            return None

        raw_output = res.stderr + "\n" + res.stdout
        clean_output = strip_ansi(raw_output)

        # Guard again against unknown option messages in case exit code was non-zero
        if any(kw in clean_output.lower() for kw in ["unknown option", "invalid option", "unrecognized option", "unknown flag"]):
            return None

        if res.returncode == 0:
            return []

        # Nonzero exit case: classify failure ONLY if recognized parser diagnostics exist
        errors = []
        for line in clean_output.splitlines():
            line_str = line.strip()
            if is_recognized_parser_diagnostic(line_str):
                errors.append(f"Hyprland Parser Error: {line_str}")

        if not errors:
            # Non-zero exit code without recognized parser diagnostics (e.g. headless environment display error)
            # Fall back to internal structural validator
            return None

        return errors
    except Exception:
        # Fallback to internal validator if process invocation failed
        return None


def validate_lua_file(file_path: Path) -> list[str]:
    errors = []
    if not file_path.exists():
        return errors

    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        return errors

    # Check if lua binary is available for syntax check
    lua_bin = shutil.which("lua") or shutil.which("luajit")
    if lua_bin:
        try:
            res = subprocess.run([lua_bin, "-e", f"assert(loadfile('{file_path}'))()"], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                errors.append(f"Lua Syntax Error: {res.stderr.strip()}")
                return errors
        except Exception:
            pass

    # Structural Lua checks
    lines = content.splitlines()
    brace_depth = 0
    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.split('--')[0].strip()
        if not line:
            continue
        brace_depth += line.count('{') - line.count('}')
        if brace_depth < 0:
            errors.append(f"Line {idx}: Unmatched closing brace in Lua config")
            brace_depth = 0

    if brace_depth != 0:
        errors.append("Unclosed table brace in Lua configuration file")

    return errors


def validate_conf_file(file_path: Path, target_version: str = "0.45.0") -> list[str]:
    errors = []
    if not file_path.exists():
        return errors

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return [f"Could not read file {file_path}: {e}"]

    in_block = False
    block_type = None
    block_name = None
    in_match = False
    brace_depth = 0

    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.split('#')[0].strip()
        if not line:
            continue

        # Check block structures: windowrule name { ... }, layerrule name { ... }, workspace name { ... }
        block_match = re.match(r'^(windowrule|layerrule|workspace)\s+([a-zA-Z0-9_\-]+)\s*\{', line)
        if block_match:
            in_block = True
            block_type = block_match.group(1)
            block_name = block_match.group(2)
            brace_depth += 1
            continue

        if line == 'match {' and in_block:
            in_match = True
            brace_depth += 1
            continue

        if line == '}':
            if brace_depth > 0:
                brace_depth -= 1
            else:
                errors.append(f"Line {idx}: Unexpected closing brace '}}'")
            if in_match and brace_depth == 1:
                in_match = False
            elif in_block and brace_depth == 0:
                in_block = False
                block_type = None
                block_name = None
            continue

        # Inside match block validation
        if in_match:
            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip()
                if key in ("class", "title", "initialClass", "initialTitle", "namespace"):
                    clean_pattern = val
                    if clean_pattern.startswith('^(') and clean_pattern.endswith(')$'):
                        clean_pattern = clean_pattern[2:-2]
                    elif clean_pattern.startswith('^'):
                        clean_pattern = clean_pattern[1:]
                    elif clean_pattern.endswith('$'):
                        clean_pattern = clean_pattern[:-1]
                    if not check_regex_validity(clean_pattern):
                        errors.append(f"Line {idx}: Invalid regex pattern '{val}' for property '{key}'")
            else:
                errors.append(f"Line {idx}: Missing '=' in match definition: '{line}'")
            continue

        # Line-based rule check
        if '=' in line and not in_block:
            directive, body = line.split('=', 1)
            directive = directive.strip()
            body = body.strip()

            if directive == "windowrulev2":
                # Deprecated in newer Hyprland
                ver_parts = [int(p) for p in target_version.split('.')] if target_version else [0, 45, 0]
                if ver_parts >= [0, 45, 0]:
                    errors.append(
                        f"Line {idx}: Deprecated 'windowrulev2' syntax used. "
                        f"Newer Hyprland ({target_version}) requires named windowrule block syntax "
                        f"('windowrule <name> {{ match {{ ... }} ... }}') or declarative match syntax."
                    )
            elif directive in ("windowrule", "layerrule", "workspace"):
                # Single line directive
                pass

    if brace_depth != 0:
        errors.append(f"Unclosed block brace in {file_path} (depth={brace_depth})")

    return errors


def validate_file(file_path: Path, is_lua: bool = False, hyprland_bin: str | None = None, target_version: str = "0.45.0") -> list[str]:
    if not file_path.exists():
        return []

    # Attempt native installed Hyprland parser first for .conf files
    if not is_lua:
        installed_errors = validate_with_installed_parser(file_path, hyprland_bin=hyprland_bin)
        if installed_errors is not None:
            return installed_errors
        return validate_conf_file(file_path, target_version=target_version)
    else:
        return validate_lua_file(file_path)


def main():
    parser = argparse.ArgumentParser(description="Validate Hyprland window/layer/workspace rules")
    parser.add_argument("files", nargs="*", help="Rule files to validate")
    parser.add_argument("--strict", action="store_true", help="Exit with non-zero status on validation errors")
    parser.add_argument("--lua", action="store_true", help="Validate in Lua mode")
    parser.add_argument("--hyprland-bin", type=str, help="Path to Hyprland executable parser")
    parser.add_argument("--hyprland-version", type=str, default="0.45.0", help="Target Hyprland version for version-aware checks")
    args = parser.parse_args()

    # Determine installed version if hyprland is present
    installed_ver = get_hyprland_installed_version(args.hyprland_bin or "hyprland")
    target_ver = installed_ver or args.hyprland_version

    files_to_check = []
    if args.files:
        files_to_check = [Path(f) for f in args.files]
    else:
        script_dir = Path(__file__).resolve().parent
        home = Path.home()
        files_to_check = [
            script_dir / "../hyprland/rules.conf",
            script_dir / "../hyprland/rules.lua",
            home / ".config/caelestia/hypr-user.conf",
            home / ".config/caelestia/hypr-user.lua",
        ]

    total_errors = 0
    for file_path in files_to_check:
        if not file_path.exists():
            continue

        is_lua_file = args.lua or file_path.suffix == ".lua"
        errors = validate_file(
            file_path,
            is_lua=is_lua_file,
            hyprland_bin=args.hyprland_bin,
            target_version=target_ver,
        )

        if errors:
            total_errors += len(errors)
            print(f"[RULE VALIDATION WARNING] Issues found in {file_path}:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print(f"[RULE VALIDATION OK] {file_path} syntax valid.", file=sys.stderr)

    if args.strict and total_errors > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
