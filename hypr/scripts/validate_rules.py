#!/usr/bin/env python3
"""
Hyprland Window & Layer Rule Syntax Validator

Validates declarative window rules, layer rules, and workspace rules for Caelestia/Hyprland.
Identifies legacy or invalid match directives (e.g., match:class), boolean rule syntax,
and syntax errors in core rules and user overrides without blocking desktop load.
"""

import sys
import os
import re
from pathlib import Path

# Legacy or invalid keywords/prefixes and their suggestions
INVALID_MATCH_PREFIX = re.compile(r'\bmatch:[a-zA-Z_]+\b')

DEPRECATED_KEYWORDS = [
    (re.compile(r'\bfloat\s+(true|false)\b'), "'float' should not have boolean parameters (use 'float' in rules, or 'floating:1'/'floating:0' in match criteria)"),
    (re.compile(r'\bcenter\s+(true|1)\b'), "'center' should not have parameters (use 'center')"),
    (re.compile(r'\bopaque\s+(true|false)\b'), "'opaque' should not have boolean parameters (use 'opaque')"),
    (re.compile(r'\bno_blur\b'), "'no_blur' is deprecated or invalid (use 'noblur')"),
    (re.compile(r'\bno_dim\b'), "'no_dim' is deprecated or invalid (use 'nodim')"),
    (re.compile(r'\bno_shadow\b'), "'no_shadow' is deprecated or invalid (use 'noshadow')"),
    (re.compile(r'\bno_initial_focus\b'), "'no_initial_focus' is deprecated or invalid (use 'noinitialfocus')"),
    (re.compile(r'\bno_anim\b'), "'no_anim' is deprecated or invalid (use 'noanim')"),
    (re.compile(r'\bignore_alpha\b'), "'ignore_alpha' is deprecated or invalid (use 'ignorealpha')"),
    (re.compile(r'\bidle_inhibit\b'), "'idle_inhibit' is deprecated or invalid (use 'idleinhibit')"),
    (re.compile(r'\bimmediate\s+true\b'), "'immediate' should not have boolean parameters (use 'immediate')"),
    (re.compile(r'\bblur\s+true\b'), "'blur' in layerrule should not have boolean parameters (use 'blur')"),
]


def check_regex_validity(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def validate_file(file_path: Path) -> list[str]:
    errors = []
    if not file_path.exists():
        return errors

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return [f"Could not read file {file_path}: {e}"]

    for idx, raw_line in enumerate(lines, 1):
        # Strip inline comments
        line = raw_line.split('#')[0].strip()
        if not line:
            continue

        # Check rule directives
        if '=' in line:
            directive, body = line.split('=', 1)
            directive = directive.strip()
            body = body.strip()

            if directive in ("windowrule", "windowrulev2", "layerrule", "workspace"):
                # 1. Check for legacy match: prefix
                match_matches = INVALID_MATCH_PREFIX.findall(body)
                if match_matches:
                    errors.append(
                        f"Line {idx}: Legacy/invalid match prefix used: {', '.join(match_matches)}. "
                        f"Hyprland rule matches should use native syntax (e.g. 'class:^(...)$', 'title:^(...)$', 'floating:1')."
                    )

                # 2. Check for deprecated / invalid keywords
                for pattern, msg in DEPRECATED_KEYWORDS:
                    if pattern.search(body):
                        errors.append(f"Line {idx}: {msg}")

                # 3. Check for syntax formatting in windowrulev2 match criteria
                if directive == "windowrulev2":
                    parts = [p.strip() for p in body.split(',')]
                    for part in parts[1:]:
                        if ':' in part:
                            key, val = part.split(':', 1)
                            key = key.strip()
                            val = val.strip()
                            if key in ("class", "title", "initialClass", "initialTitle"):
                                if val.startswith('^(') and val.endswith(')$'):
                                    inner = val[2:-2]
                                    if not check_regex_validity(inner):
                                        errors.append(f"Line {idx}: Invalid regex pattern '{inner}' in match criteria '{part}'")
        elif line.startswith(("windowrule", "windowrulev2", "layerrule", "workspace")):
            errors.append(f"Line {idx}: Missing '=' in rule definition: '{line}'")

    return errors


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate Hyprland window/layer rules")
    parser.add_argument("files", nargs="*", help="Rule files to validate")
    parser.add_argument("--strict", action="store_true", help="Exit with non-zero status on validation errors")
    args = parser.parse_args()

    files_to_check = []
    if args.files:
        files_to_check = [Path(f) for f in args.files]
    else:
        # Default targets: core system rules and user overrides
        script_dir = Path(__file__).resolve().parent
        home = Path.home()
        files_to_check = [
            script_dir / "../hyprland/rules.conf",
            home / ".config/hypr/hyprland/rules.conf",
            home / ".config/caelestia/hypr-user.conf",
        ]

    total_errors = 0
    for file_path in files_to_check:
        if not file_path.exists():
            continue
        errors = validate_file(file_path)
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
