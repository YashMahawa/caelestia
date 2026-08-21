import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import getpass

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestSyncAndInstall(unittest.TestCase):
    def test_sync_qml_refuses_root(self):
        script_path = REPO_ROOT / "bin" / "sync-caelestia-qml"
        res = subprocess.run(
            [str(script_path), "root"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Refusing to sync QML for root user", res.stderr)

    def test_sync_qml_scoped_sync_preserves_custom_files(self):
        script_path = REPO_ROOT / "bin" / "sync-caelestia-qml"
        current_user = getpass.getuser()
        
        # Test directory in user config
        user_config = Path.home() / ".config" / "quickshell"
        user_config.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=user_config, prefix="test-caelestia-") as tmpdir:
            dst_dir = Path.home() / ".config" / "quickshell" / "caelestia"
            # Backup existing dst_dir if it exists
            backup_dst = None
            if dst_dir.exists():
                backup_dst = Path.home() / ".config" / "quickshell" / "caelestia.testbackup"
                if backup_dst.exists():
                    import shutil
                    shutil.rmtree(backup_dst)
                dst_dir.rename(backup_dst)

            try:
                dst_dir.mkdir(parents=True, exist_ok=True)
                # Create a user custom file in dst
                custom_user_file = dst_dir / "user.json"
                custom_user_file.write_text('{"theme": "custom"}')

                # Create mock package source
                pkg_base = Path(tmpdir) / "etc_xdg"
                pkg_src = pkg_base / "quickshell" / "caelestia"
                pkg_src.mkdir(parents=True, exist_ok=True)
                (pkg_src / "shell.qml").write_text("// package shell")

                env = os.environ.copy()
                env["XDG_CONFIG_DIRS"] = str(pkg_base)

                res = subprocess.run(
                    [str(script_path), current_user],
                    capture_output=True,
                    text=True,
                    env=env,
                )
                self.assertEqual(res.returncode, 0)

                # Ensure user custom file was preserved (not deleted by broad tree replacement)
                self.assertTrue(custom_user_file.exists(), "Custom user file user.json was deleted!")
                self.assertEqual(custom_user_file.read_text(), '{"theme": "custom"}')

                # Ensure shell.qml was updated/copied into dst
                synced_shell = dst_dir / "shell.qml"
                self.assertTrue(synced_shell.exists())
                self.assertEqual(synced_shell.read_text(), "// package shell")
            finally:
                if dst_dir.exists():
                    import shutil
                    shutil.rmtree(dst_dir)
                if backup_dst and backup_dst.exists():
                    backup_dst.rename(dst_dir)

    def test_install_fish_contains_user_only_flags(self):
        install_script = REPO_ROOT / "install.fish"
        content = install_script.read_text(encoding="utf-8")
        self.assertIn("'no-packages'", content)
        self.assertIn("'user-only'", content)
        self.assertIn("User-only mode enabled", content)

if __name__ == "__main__":
    unittest.main()
