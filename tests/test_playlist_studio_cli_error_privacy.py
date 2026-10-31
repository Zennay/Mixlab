"""Guided local-song playlist CLI must not echo private option values on failure."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class GuidedStudioCliPrivacy(unittest.TestCase):
    def test_invalid_manual_choices_cannot_reappear_in_stderr(self):
        with tempfile.TemporaryDirectory(prefix='mixlab-studio-cli-') as root:
            marker = 'SYNTHETIC_LOCAL_MUSIC_SOURCE_904'
            music = Path(root, 'private-music')
            music.mkdir()
            manifest = music / (marker + '.json')
            session = Path(root, 'new-studio')
            choices = [
                [str(music), str(manifest), str(session), '--family', marker],
                [str(music), str(manifest), str(session), '--family', 'baseline', '--' + marker],
                [str(music), str(manifest), str(session), '--beats', marker],
            ]
            for args in choices:
                with self.subTest(args=args[-2:]):
                    process = subprocess.run(
                        [sys.executable, '-m', 'mixlab.playlist_studio', *args],
                        cwd=Path(__file__).resolve().parents[1],
                        capture_output=True, text=True, timeout=15)
                    self.assertEqual(process.returncode, 2, process.stderr)
                    self.assertEqual(process.stdout, '')
                    self.assertNotIn(marker, process.stderr)
                    self.assertNotIn(str(root), process.stderr)
                    self.assertNotIn('Traceback', process.stderr)
                    self.assertIn('details withheld', process.stderr)
                    self.assertLessEqual(len(process.stderr), 150)

if __name__ == '__main__':
    unittest.main()
