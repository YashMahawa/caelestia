import importlib.util
import json
import os
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch

# Dynamically import caelestia-voice and caelestia-voice-settings
bin_dir = Path(__file__).resolve().parent.parent / "bin"

loader_voice = SourceFileLoader("caelestia_voice", str(bin_dir / "caelestia-voice"))
spec_voice = importlib.util.spec_from_loader("caelestia_voice", loader_voice)
voice = importlib.util.module_from_spec(spec_voice)
sys.modules["caelestia_voice"] = voice
spec_voice.loader.exec_module(voice)

loader_settings = SourceFileLoader("caelestia_voice_settings", str(bin_dir / "caelestia-voice-settings"))
spec_settings = importlib.util.spec_from_loader("caelestia_voice_settings", loader_settings)
voice_settings = importlib.util.module_from_spec(spec_settings)
sys.modules["caelestia_voice_settings"] = voice_settings
spec_settings.loader.exec_module(voice_settings)


class TestVoiceBridgeAndFallback(unittest.TestCase):
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_native_ipc_success(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/caelestia"
        mock_run.return_value = MagicMock(returncode=0, stdout='{"status":"listening"}', stderr="")

        # Test try_native_voice_ipc status
        with patch("builtins.print") as mock_print:
            result = voice.try_native_voice_ipc("status")
            self.assertTrue(result)
            mock_print.assert_called_with('{"status":"listening"}')

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_native_ipc_failure_triggers_fallback(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/caelestia"
        # Simulate unknown command error from native CLI
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error: unknown command 'voice'")

        result = voice.try_native_voice_ipc("toggle")
        self.assertFalse(result)

    @patch("shutil.which")
    def test_native_ipc_missing_binary(self, mock_which):
        mock_which.return_value = None
        result = voice.try_native_voice_ipc("toggle")
        self.assertFalse(result)

    def test_standalone_state_write_and_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with patch.object(voice, "STATE_DIR", tmppath), \
                 patch.object(voice, "STATE", tmppath / "voice-state.json"):
                voice.write_state("listening", "Listening…", detail="Press F9 again")
                self.assertTrue((tmppath / "voice-state.json").exists())
                data = json.loads((tmppath / "voice-state.json").read_text())
                self.assertEqual(data["status"], "listening")
                self.assertEqual(data["message"], "Listening…")

    def test_standalone_transcription_config_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with patch.object(voice, "CONFIG", tmppath / "nonexistent.json"):
                model, prompt = voice.transcription_config()
                self.assertEqual(model, "gemini-3.1-flash-lite")
                self.assertEqual(prompt, voice.DEFAULT_PROMPT)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_settings_native_ipc_fallback(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/caelestia"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="IPC connection failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with patch.object(voice_settings, "CONFIG", tmppath / "voice-typing.json"), \
                 patch.object(voice_settings, "lookup", return_value=None):
                with patch("builtins.print") as mock_print:
                    voice_settings.status()
                    mock_print.assert_called_once()
                    out = json.loads(mock_print.call_args[0][0])
                    self.assertEqual(out["keys"], [False, False, False])
                    self.assertEqual(out["model"], "gemini-3.1-flash-lite")

    def test_settings_save_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            config_file = tmppath / "voice-typing.json"
            new_prompt = "Transcribe the user speech accurately without any filler words or preamble."
            with patch.object(voice_settings, "CONFIG", config_file), \
                 patch("shutil.which", return_value=None):
                voice_settings.save_prompt(new_prompt)
                self.assertTrue(config_file.exists())
                data = json.loads(config_file.read_text())
                self.assertEqual(data["prompt"], new_prompt)


if __name__ == "__main__":
    unittest.main()
