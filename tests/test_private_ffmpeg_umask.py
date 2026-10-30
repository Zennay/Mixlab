"""The child decoder must not inherit permissive private WAV permissions."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

from mixlab.media_import import _transcode


@unittest.skipUnless(os.name == "posix", "POSIX umask is relevant on Linux/macOS")
class PrivateFFmpegOutputTests(unittest.TestCase):
    def test_child_wav_is_private_at_birth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decoder = root / "synthetic_decoder.py"
            decoder.write_text(
                "#!" + sys.executable + "\n"
                "from pathlib import Path\n"
                "import stat, sys\n"
                "target = Path(sys.argv[-1])\n"
                "with target.open('xb') as output:\n"
                "    mode = stat.S_IMODE(target.stat().st_mode)\n"
                "    output.write(b'SYNTHETIC')\n"
                "target.with_suffix('.mode').write_text(oct(mode))\n"
            )
            decoder.chmod(0o700)
            source = root / "source.wav"
            source.write_bytes(b"SYNTHETIC")
            target = root / "decoded.wav"
            before = os.umask(0)
            try:
                _transcode(source, target, str(decoder), 30)
                self.assertEqual((root / "decoded.mode").read_text(), "0o600")
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                self.assertEqual(os.umask(0), 0, "Decoder must not alter parent umask")
                with self.assertRaises(ValueError):
                    _transcode(source, target, str(decoder), 30)
                self.assertEqual(target.read_bytes(), b"SYNTHETIC")
            finally:
                os.umask(before)


if __name__ == "__main__":
    unittest.main()
