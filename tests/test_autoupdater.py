import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from mybatis_migrator.autoupdater import AutoUpdater


class TestAutoUpdater(unittest.TestCase):
    def setUp(self):
        self.updater = AutoUpdater(
            app_name="test-app",
            current_version="1.0.0",
            github_repo="owner/repo",
            show_progress=True,
        )

    def test_init_defaults_and_custom(self):
        self.assertEqual(self.updater.app_name, "test-app")
        self.assertEqual(self.updater.current_version, "1.0.0")
        self.assertEqual(self.updater.version_url, "https://owner.github.io/repo/version.json")
        self.assertTrue(self.updater.show_progress)

        updater_no_prog = AutoUpdater(
            app_name="test-app",
            current_version="v2.0.0",
            github_repo="owner/repo",
            show_progress=False,
        )
        self.assertFalse(updater_no_prog.show_progress)
        self.assertEqual(updater_no_prog.current_version, "2.0.0")

    def test_parse_version(self):
        self.assertEqual(self.updater._parse_version("1.0.0"), (1, 0, 0))
        self.assertEqual(self.updater._parse_version("v2.3.4.5"), (2, 3, 4, 5))
        self.assertEqual(self.updater._parse_version("invalid"), (0,))

    def test_verify_hash(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"hello world\n")
            temp_path = f.name

        try:
            # sha256 of "hello world\n"
            # python: import hashlib; hashlib.sha256(b"hello world\n").hexdigest()
            import hashlib
            expected = hashlib.sha256(b"hello world\n").hexdigest()

            self.assertTrue(self.updater._verify_hash(temp_path, expected, "sha256"))
            self.assertFalse(self.updater._verify_hash(temp_path, "wrong_hash", "sha256"))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch.object(AutoUpdater, "_check_internet", return_value=False)
    def test_check_for_update_offline(self, mock_check_internet):
        has_update = self.updater.check_for_update()
        self.assertFalse(has_update)

    @patch("urllib.request.urlopen")
    def test_download_silent(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b"chunk1", b"chunk2", b""]
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_path = os.path.join(tmpdir, "setup.exe")
            req = MagicMock()
            success = self.updater._download_silent(req, setup_path)

            self.assertTrue(success)
            self.assertTrue(os.path.exists(setup_path))
            with open(setup_path, "rb") as f:
                content = f.read()
            self.assertEqual(content, b"chunk1chunk2")


if __name__ == "__main__":
    unittest.main()
