"""Real subprocess regression: private input names stay out of failed DJ CLI output."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class PartyMixCliFailurePrivacy(unittest.TestCase):
    def test_private_inputs_are_not_echoed_for_missing_source_and_invalid_options(self):
        with tempfile.TemporaryDirectory(prefix='mixlab-party-cli-') as directory:
            marker = 'FICTIONAL_PRIVATE_TRACK_VALUE_902'
            music = Path(directory) / 'original-music'
            music.mkdir()
            manifest = music / (marker + '.json')
            session = Path(directory) / 'studio'
            output = Path(directory) / 'out.wav'
            commands = [
                [str(manifest), str(session), str(output), '--family', 'baseline', '--preview'],
                [str(manifest), str(session), str(output), '--family', marker, '--preview'],
                [str(manifest), str(session), str(output), '--family', 'baseline', '--'+marker],
            ]
            for args in commands:
                with self.subTest(args=args[-2:]):
                    process = subprocess.run(
                        [sys.executable, '-m', 'mixlab.party_mix', *args],
                        capture_output=True, text=True, timeout=12,
                        cwd=Path(__file__).resolve().parents[1])
                    self.assertEqual(process.returncode, 2, process.stderr)
                    self.assertEqual(process.stdout, '')
                    self.assertNotIn(marker, process.stderr)
                    self.assertNotIn(str(manifest), process.stderr)
                    self.assertNotIn(str(directory), process.stderr)
                    self.assertNotIn('Traceback', process.stderr)
                    self.assertIn('details withheld', process.stderr)
                    self.assertLessEqual(len(process.stderr), 150)

if __name__ == '__main__':
    unittest.main()
