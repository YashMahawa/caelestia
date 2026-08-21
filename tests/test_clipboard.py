import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

# Import caelestia-clipboard module dynamically
script_path = Path(__file__).resolve().parent.parent / "bin" / "caelestia-clipboard"
loader = SourceFileLoader("caelestia_clipboard", str(script_path))
spec = importlib.util.spec_from_loader("caelestia_clipboard", loader)
clipboard = importlib.util.module_from_spec(spec)
sys.modules["caelestia_clipboard"] = clipboard
spec.loader.exec_module(clipboard)


class TestMimeTypeFilter(unittest.TestCase):
    def test_is_sensitive_type(self):
        # Sensitive MIME types
        self.assertTrue(clipboard.is_sensitive_type(["text/plain", "x-kde-passwordManagerHint"]))
        self.assertTrue(clipboard.is_sensitive_type(["text/x-moz-password", "text/plain"]))
        self.assertTrue(clipboard.is_sensitive_type(["application/x-kde-passwordManagerHint"]))
        self.assertTrue(clipboard.is_sensitive_type(["secret"]))
        self.assertTrue(clipboard.is_sensitive_type(["x-kde-passwordmanagerhint;charset=utf-8"]))
        self.assertTrue(clipboard.is_sensitive_type(["application/x-keepassxc-password"]))

        # Non-sensitive MIME types
        self.assertFalse(clipboard.is_sensitive_type(["text/plain"]))
        self.assertFalse(clipboard.is_sensitive_type(["text/plain;charset=utf-8", "text/html"]))
        self.assertFalse(clipboard.is_sensitive_type(["image/png", "image/jpeg"]))
        self.assertFalse(clipboard.is_sensitive_type(["text/uri-list"]))

        # Edge cases
        self.assertFalse(clipboard.is_sensitive_type([]))
        self.assertFalse(clipboard.is_sensitive_type(["unrecognized/type-foo"]))
        self.assertFalse(clipboard.is_sensitive_type([None, ""]))

    @patch("caelestia_clipboard.offered_types")
    def test_sensitive_capture_stdin_aborts_early(self, mock_offered_types):
        for hint in ["x-kde-passwordManagerHint", "text/x-moz-password", "secret"]:
            mock_offered_types.return_value = ["text/plain", hint]

            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                with patch.object(clipboard, "DATA", tmppath), \
                     patch.object(clipboard, "FILES", tmppath / "items"), \
                     patch.object(clipboard, "DB", tmppath / "history.sqlite3"), \
                     patch.object(clipboard, "STATE", tmppath / "clipboard-history.json"), \
                     patch.object(clipboard, "STATE_LOCK", tmppath / "clipboard-history.lock"):

                    result = clipboard.capture_stdin()
                    self.assertEqual(result, 0)

                    # Confirm zero database entries created
                    if (tmppath / "history.sqlite3").exists():
                        conn = sqlite3.connect(tmppath / "history.sqlite3")
                        count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                        conn.close()
                        self.assertEqual(count, 0)

                    # Confirm history JSON file not created or modified
                    self.assertFalse((tmppath / "clipboard-history.json").exists())

    @patch("caelestia_clipboard.offered_types")
    def test_sensitive_capture_aborts_early(self, mock_offered_types):
        mock_offered_types.return_value = ["text/plain", "x-kde-passwordManagerHint"]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with patch.object(clipboard, "DATA", tmppath), \
                 patch.object(clipboard, "FILES", tmppath / "items"), \
                 patch.object(clipboard, "DB", tmppath / "history.sqlite3"), \
                 patch.object(clipboard, "STATE", tmppath / "clipboard-history.json"), \
                 patch.object(clipboard, "STATE_LOCK", tmppath / "clipboard-history.lock"):

                result = clipboard.capture()
                self.assertEqual(result, 0)

                # Confirm zero database entries created
                if (tmppath / "history.sqlite3").exists():
                    conn = sqlite3.connect(tmppath / "history.sqlite3")
                    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                    conn.close()
                    self.assertEqual(count, 0)

                self.assertFalse((tmppath / "clipboard-history.json").exists())

    @patch("caelestia_clipboard.offered_types")
    def test_empty_or_unrecognized_mime_types_no_crash(self, mock_offered_types):
        for empty_or_unrecognized in [[], ["unknown/mime-type-x"], [" "], [None]]:
            mock_offered_types.return_value = empty_or_unrecognized
            fake_stdin = unittest.mock.MagicMock()
            fake_stdin.buffer = io.BytesIO(b"")

            with tempfile.TemporaryDirectory() as tmpdir:
                tmppath = Path(tmpdir)
                with patch.object(clipboard, "DATA", tmppath), \
                     patch.object(clipboard, "FILES", tmppath / "items"), \
                     patch.object(clipboard, "DB", tmppath / "history.sqlite3"), \
                     patch.object(clipboard, "STATE", tmppath / "clipboard-history.json"), \
                     patch.object(clipboard, "STATE_LOCK", tmppath / "clipboard-history.lock"), \
                     patch.object(sys, "stdin", fake_stdin):

                    # Should run without raising any exceptions
                    try:
                        result = clipboard.capture_stdin()
                        self.assertEqual(result, 0)
                    except Exception as e:
                        self.fail(f"capture_stdin raised exception {e} on input {empty_or_unrecognized}")

    @patch("caelestia_clipboard.offered_types")
    def test_normal_text_capture_stdin(self, mock_offered_types):
        mock_offered_types.return_value = ["text/plain;charset=utf-8"]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            fake_stdin = unittest.mock.MagicMock()
            fake_stdin.buffer = io.BytesIO(b"regular test text")

            with patch.object(clipboard, "DATA", tmppath), \
                 patch.object(clipboard, "FILES", tmppath / "items"), \
                 patch.object(clipboard, "DB", tmppath / "history.sqlite3"), \
                 patch.object(clipboard, "STATE", tmppath / "clipboard-history.json"), \
                 patch.object(clipboard, "STATE_LOCK", tmppath / "clipboard-history.lock"), \
                 patch.object(sys, "stdin", fake_stdin):

                result = clipboard.capture_stdin()
                self.assertEqual(result, 0)

                # Confirm database entry created
                conn = sqlite3.connect(tmppath / "history.sqlite3")
                row = conn.execute("SELECT text FROM items").fetchone()
                conn.close()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "regular test text")

                # Confirm history JSON created
                self.assertTrue((tmppath / "clipboard-history.json").exists())
                data = json.loads((tmppath / "clipboard-history.json").read_text())
                self.assertEqual(data[0]["text"], "regular test text")


if __name__ == "__main__":
    unittest.main()
