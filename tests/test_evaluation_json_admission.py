"""Synthetic-only regression tests for the isolated ML-05 JSON admission gate.

No real listening pack, external music, hosted model, network or VPS.
The existing ML-05 evaluation integration remains owner-controlled.
"""
import json
import os
from pathlib import Path
import tempfile
import time
import traceback
import unittest
from unittest import mock

from mixlab.evaluation import json_admission
from mixlab.evaluation.json_admission import (
    MAX_EVALUATION_JSON_BYTES, load_bounded_json,
)


class EvaluationJsonAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ml05-fd-json-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.source = self.folder / "private-rating.json"
        self.source.write_text('{"schema_version":1,"reviewer":"synthetic"}',
                               encoding="utf-8")

    def test_valid_json_and_existing_semantic_types_are_preserved(self):
        record = load_bounded_json(self.source)
        self.assertEqual(record, {"schema_version": 1,
                                  "reviewer": "synthetic"})
        for value in ('[]', 'null', '"ok"', '5'):
            with self.subTest(value=value):
                self.source.write_text(value, encoding="utf-8")
                self.assertEqual(load_bounded_json(self.source), json.loads(value))

    def test_depth_boundary_and_quoted_delimiters_are_not_nesting(self):
        at_limit = "[" * 64 + "0" + "]" * 64
        self.source.write_text(at_limit, encoding="utf-8")
        self.assertEqual(load_bounded_json(self.source), json.loads(at_limit))
        past_limit = "[" * 65 + "0" + "]" * 65
        self.source.write_text(past_limit, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nesting"):
            load_bounded_json(self.source)
        note = "brackets [ { } ] then quoted " + chr(34) + " backslash " + chr(92)
        self.source.write_text(json.dumps({"note": note}), encoding="utf-8")
        self.assertEqual(load_bounded_json(self.source), {"note": note})

    def test_reject_duplicate_keys_at_nested_level(self):
        self.source.write_text('{"a":{"x":1,"x":2}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_bounded_json(self.source)

    def test_reject_nonfinite_and_invalid_utf8(self):
        for word in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(word=word):
                self.source.write_text('{"a":' + word + '}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Nonfinite"):
                    load_bounded_json(self.source)
        self.source.write_bytes(b'{"a":"\xff"}')
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            load_bounded_json(self.source)

    def test_exponent_overflow_floats_are_rejected_not_infinite(self):
        for payload in ("1e999", "-1e999", '{"a":1e999}',
                        '{"a":-9.1e999}', "[1.0e500, 3]"):
            with self.subTest(payload=payload):
                self.source.write_text(payload, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Nonfinite"):
                    load_bounded_json(self.source)
        for payload in ('{"value":1.25}', "[1e2, -0.125]"):
            with self.subTest(valid=payload):
                self.source.write_text(payload, encoding="utf-8")
                self.assertEqual(load_bounded_json(self.source),
                                 json.loads(payload))

    def test_reject_deep_parser_recursion_as_validation_error(self):
        self.source.write_text("[" * 1500 + "0" + "]" * 1500,
                               encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nesting"):
            load_bounded_json(self.source)

    def test_refuse_directory_missing_file_and_final_symlink(self):
        linked = self.folder / "private-linked.json"
        linked.symlink_to(self.source)
        for path in (self.folder, self.folder / "missing.json", linked):
            with self.subTest(path=path.name):
                with self.assertRaises(ValueError):
                    load_bounded_json(path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_fifo_rejected_without_waiting_for_writer(self):
        fifo = self.folder / "rating-fifo"
        os.mkfifo(fifo)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "regular file"):
            load_bounded_json(fifo)
        self.assertLess(time.monotonic() - started, 2)

    def test_sparse_oversize_and_exact_limit(self):
        with self.source.open("wb") as output:
            output.truncate(MAX_EVALUATION_JSON_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "4 MiB"):
            load_bounded_json(self.source)
        # The full 4 MiB boundary is valid if JSON whitespace fills it.
        self.source.write_bytes(b"{}" + b" " *
                                (MAX_EVALUATION_JSON_BYTES - 2))
        self.assertEqual(load_bounded_json(self.source), {})

    def test_growth_during_read_rejected_even_after_bounded_content(self):
        normal_read = json_admission._read_bounded

        def read_then_grow(fd):
            data = normal_read(fd)
            with self.source.open("ab") as output:
                output.write(b" ")
            return data

        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=read_then_grow):
            with self.assertRaisesRegex(ValueError, "changed"):
                load_bounded_json(self.source)

    def test_identical_bytes_replacement_detected_by_inode(self):
        replacement = self.folder / "new-rating.json"
        replacement.write_bytes(self.source.read_bytes())
        normal_read = json_admission._read_bounded

        def swap_after_read(fd):
            data = normal_read(fd)
            os.replace(replacement, self.source)
            return data

        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=swap_after_read):
            with self.assertRaisesRegex(ValueError, "changed"):
                load_bounded_json(self.source)

    def test_open_race_detected_before_read(self):
        replacement = self.folder / "another-rating.json"
        replacement.write_bytes(self.source.read_bytes())
        real_open = os.open

        def swap_before_open(path, flags, *args, **kwargs):
            os.replace(replacement, self.source)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(json_admission.os, "open",
                               side_effect=swap_before_open):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                load_bounded_json(self.source)

    def test_sensitive_filesystem_error_cannot_leak_in_traceback(self):
        with mock.patch.object(json_admission.os, "stat",
                               side_effect=PermissionError(
                                   "SECRET_PRIVATE_AUDIO_PATH")):
            with self.assertRaises(ValueError) as caught:
                load_bounded_json(self.source)
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn("SECRET_PRIVATE_AUDIO_PATH", rendered)
        self.assertNotIn("SECRET_PRIVATE_AUDIO_PATH", str(caught.exception))

    def test_no_second_source_open_and_bounded_os_reads(self):
        original_open = os.open
        opened = []
        reads = []
        original_read = os.read

        def audited_open(path, flags, *args, **kwargs):
            opened.append((path, flags))
            return original_open(path, flags, *args, **kwargs)

        def audited_read(fd, size):
            reads.append(size)
            return original_read(fd, size)

        with mock.patch.object(json_admission.os, "open",
                               side_effect=audited_open):
            with mock.patch.object(json_admission.os, "read",
                                   side_effect=audited_read):
                self.assertEqual(load_bounded_json(self.source)["reviewer"],
                                 "synthetic")
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0][1] & os.O_NOFOLLOW)
        self.assertTrue(opened[0][1] & os.O_NONBLOCK)
        self.assertTrue(reads)
        self.assertTrue(all(1 <= size <= 65536 for size in reads))


if __name__ == "__main__":
    unittest.main()
