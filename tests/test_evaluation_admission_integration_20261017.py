"""Integration tests for the existing ML-05 evaluator's bounded JSON gate.

Synthetic JSON only; no private audio, human claims, production or deployment.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from mixlab.evaluation import _load, verify_pack, aggregate
from mixlab.cli import fixture, benchmark
from mixlab.ingest import MAX_BYTES
from mixlab.evaluation import json_admission


class EvaluationAdmissionIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-eval-integration-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "synthetic-rating.json"
        self.path.write_text('{"reviewer":"synthetic","ratings":[]}', encoding="utf-8")

    def test_real_evaluator_uses_strict_json_gate(self):
        self.assertEqual(_load(self.path)["reviewer"], "synthetic")
        self.path.write_text('{"ratings":[],"ratings":[1]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            _load(self.path)

    def test_symlink_and_directory_fail_closed(self):
        link = self.root / "alias.json"
        link.symlink_to(self.path)
        for path in (link, self.root):
            with self.subTest(kind=path.name), self.assertRaises(ValueError):
                _load(path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_fifo_rejected_before_blocking_read(self):
        fifo = self.root / "private-reviewer-pipe.json"
        os.mkfifo(fifo)
        started = time.monotonic()
        with self.assertRaisesRegex(ValueError, "regular file"):
            _load(fifo)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_oversize_rejected_without_reading_payload(self):
        with self.path.open("wb") as f:
            f.truncate(json_admission.MAX_EVALUATION_JSON_BYTES + 1)
        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=AssertionError("should not read")):
            with self.assertRaisesRegex(ValueError, "4 MiB"):
                _load(self.path)

    def test_path_replacement_rejected_in_real_evaluator(self):
        original_read = json_admission._read_bounded
        replacement = self.root / "replacement.json"
        replacement.write_bytes(self.path.read_bytes())
        def swap_after_read(fd):
            data = original_read(fd)
            os.replace(replacement, self.path)
            return data
        with mock.patch.object(json_admission, "_read_bounded",
                               side_effect=swap_after_read):
            with self.assertRaisesRegex(ValueError, "changed"):
                _load(self.path)

    def test_cli_missing_private_pack_path_never_disclosed(self):
        secret = "PRIVATE_REVIEWER_SECRET_7835"
        missing = self.root / secret / "unavailable-pack"
        proc = subprocess.run(
            [sys.executable, "-m", "mixlab.evaluation", str(missing),
             str(self.path)], capture_output=True, text=True, timeout=8)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("invalid or unavailable private input", proc.stderr)
        self.assertNotIn(secret, proc.stdout + proc.stderr)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_cli_invalid_private_rating_path_never_disclosed(self):
        # A structurally invalid synthetic pack also exercises generic CLI
        # errors without exposing the pack's private absolute pathname.
        pack = self.root / "SECRET_RATING_SOURCE_781"
        (pack / "private").mkdir(parents=True)
        (pack / "receipt.json").write_text('{"pack_id":"placeholder"}')
        (pack / "private" / "evidence.json").write_text('{"renders":[]}')
        (pack / "private" / "answer-key.json").write_text('[]')
        proc = subprocess.run(
            [sys.executable, "-m", "mixlab.evaluation", str(pack),
             str(self.path)], capture_output=True, text=True, timeout=8)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("SECRET_RATING_SOURCE_781", proc.stdout + proc.stderr)
        self.assertNotIn(str(self.root), proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


class FrozenReviewAudioAdmissionTests(unittest.TestCase):
    """Frozen synthetic review WAVs must remain bounded regular inputs."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mixlab-eval-audio-")
        cls.root = Path(cls.temp.name)
        manifest = fixture(cls.root / "library")
        cls.pack = cls.root / "pack"
        benchmark(manifest, cls.pack, seed=17)
        cls.wav = cls.pack / "review" / "trial-001-A.wav"

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_mutation_between_pack_verification_and_confounds_rejected(self):
        # The evaluator opens the same listening WAVs twice: once for the
        # frozen SHA check, then independently in compare_wavs. A writer
        # changing audio at the second stage must not yield a report based
        # on nonfrozen samples. No private/reviewer input is used.
        answers = json.loads((self.pack / "private/answer-key.json").read_text())
        receipt = json.loads((self.pack / "receipt.json").read_text())
        rating_path = self.root / "synthetic-midscan-reviewer.json"
        rating_path.write_text(json.dumps({
            "schema_version": 1, "pack_id": receipt["pack_id"],
            "reviewer": "synthetic-midscan",
            "ratings": [{"trial": entry["trial"], "preference": "Tie"}
                        for entry in answers],
        }), encoding="utf-8")
        original = self.wav.read_bytes()
        called = 0

        def replace_audio_on_comparison(_base, _candidates):
            nonlocal called
            called += 1
            if called == 1:
                changed = bytearray(original)
                changed[-2] ^= 0x01
                self.wav.write_bytes(changed)
            return {"candidates": [{
                "level_comparable_for_blind_ab": True,
                "warnings": [],
            }]}

        try:
            with mock.patch("mixlab.quality.compare_wavs",
                            side_effect=replace_audio_on_comparison):
                with self.assertRaisesRegex(ValueError, "changed|freeze|mutation"):
                    aggregate(self.pack, [rating_path])
            self.assertEqual(called, len(answers))
        finally:
            self.wav.write_bytes(original)
            rating_path.unlink(missing_ok=True)

    def test_all_synthetic_render_permissions_keep_synthetic_limitation(self):
        # evidence.kind is not included in pack-id. Changing it must not
        # erase the synthetic-only limitation if every source declaration
        # still says synthetic and the listening audio is unchanged.
        evidence_path = self.pack / "private" / "evidence.json"
        receipt_path = self.pack / "receipt.json"
        key_path = self.pack / "private" / "answer-key.json"
        original = evidence_path.read_bytes()
        rating_path = self.root / "synthetic-listener.json"
        try:
            evidence = json.loads(original)
            self.assertEqual(evidence["kind"], "synthetic-smoke-only")
            self.assertTrue(all(
                entry["metrics"]["source_permission_declarations"] ==
                {"a": "synthetic", "b": "synthetic"}
                for entry in evidence["renders"]
            ))
            evidence["kind"] = "development-pilot"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            receipt = json.loads(receipt_path.read_text())
            answers = json.loads(key_path.read_text())
            rating_path.write_text(json.dumps({
                "schema_version": 1, "pack_id": receipt["pack_id"],
                "reviewer": "synthetic",
                "ratings": [{"trial": row["trial"], "preference": "Tie"}
                            for row in answers]
            }), encoding="utf-8")
            outcome = aggregate(self.pack, [rating_path])
            self.assertIn(
                "synthetic input cannot establish musical preference",
                outcome["limitations"])
            self.assertFalse(outcome["milestone_pass"])
        finally:
            evidence_path.write_bytes(original)
            rating_path.unlink(missing_ok=True)

    def test_receipt_cannot_spoof_completed_human_acceptance(self):
        # The immutable renderer always records a non-listener-validated
        # status. A post-freeze edit to this unhashed public field must not
        # masquerade as actual music/listener validation.
        path = self.pack / "receipt.json"
        original = path.read_bytes()
        try:
            baseline = json.loads(original)
            self.assertEqual(baseline["status"],
                             "rendered-not-listener-validated")
            for value in ("human-listening-passed", "release-approved",
                          True, None):
                with self.subTest(value=value):
                    candidate = dict(baseline)
                    candidate["status"] = value
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    with mock.patch(
                        "mixlab.evaluation.inspect_wav_and_digest",
                        side_effect=AssertionError("WAV opened")
                    ) as inspect:
                        with self.assertRaisesRegex(ValueError, "status"):
                            verify_pack(self.pack)
                        inspect.assert_not_called()
        finally:
            path.write_bytes(original)

    def test_receipt_counts_require_exact_json_integer_type(self):
        # A numeric float such as 3.0 compares equal to int 3 in Python,
        # but it must not be admitted as an integer count in the frozen
        # experimental evidence envelope.
        path = self.pack / "receipt.json"
        original = path.read_bytes()
        try:
            baseline = json.loads(original)
            for field in ("trial_count", "render_count"):
                count = baseline[field]
                self.assertIs(type(count), int)
                for replacement in (float(count), str(count), None):
                    with self.subTest(field=field, replacement=replacement):
                        mutated = dict(baseline)
                        mutated[field] = replacement
                        path.write_text(json.dumps(mutated), encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "count"):
                            verify_pack(self.pack)
        finally:
            path.write_bytes(original)

    def test_duplicate_pair_candidate_cannot_double_count_blind_trials(self):
        # Construct a fully internally consistent forged pack: fresh
        # SHA-bound answer key, matching receipt/evidence, and byte-identical
        # review WAVs. The second trial has a different ID but the *same*
        # pair and candidate family, which would overweight one result.
        import hashlib
        import shutil
        key_path = self.pack / "private" / "answer-key.json"
        evidence_path = self.pack / "private" / "evidence.json"
        receipt_path = self.pack / "receipt.json"
        paths = (key_path, evidence_path, receipt_path)
        originals = {path: path.read_bytes() for path in paths}
        clone_id = "trial-004"
        copies = [self.pack / "review" / f"{clone_id}-{label}.wav"
                  for label in ("A", "B")]
        try:
            key = json.loads(originals[key_path])
            clone = dict(key[0])
            source_id = clone["trial"]
            clone["trial"] = clone_id
            key.append(clone)
            evidence = json.loads(originals[evidence_path])
            receipt = json.loads(originals[receipt_path])
            identity = {
                "manifest": evidence["manifest_sha256"],
                "answers": key,
                "outputs": [row["output_sha256"] for row in evidence["renders"]],
            }
            pack_id = hashlib.sha256(
                json.dumps(identity, sort_keys=True).encode()).hexdigest()
            evidence["pack_id"] = receipt["pack_id"] = pack_id
            receipt["trial_count"] = len(key)
            key_path.write_text(json.dumps(key), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            for label, destination in zip(("A", "B"), copies):
                shutil.copyfile(
                    self.pack / "review" / f"{source_id}-{label}.wav",
                    destination)
            with self.assertRaisesRegex(ValueError, "Duplicate candidate"):
                verify_pack(self.pack)
        finally:
            for path in paths:
                path.write_bytes(originals[path])
            for copied in copies:
                copied.unlink(missing_ok=True)

    def test_public_receipt_and_private_evidence_bind_same_manifest_and_schema(self):
        # Otherwise a displayed pack receipt can claim a different source
        # manifest from the private identity still used for pack-id hashing.
        receipt_path = self.pack / "receipt.json"
        evidence_path = self.pack / "private" / "evidence.json"
        receipt_raw, evidence_raw = receipt_path.read_bytes(), evidence_path.read_bytes()
        try:
            receipt = json.loads(receipt_raw)
            evidence = json.loads(evidence_raw)
            invalid = (
                (receipt_path, {**receipt, "manifest_sha256": "f" * 64}),
                (receipt_path, {**receipt, "schema_version": True}),
                (receipt_path, {**receipt, "schema_version": 1.0}),
                (evidence_path, {**evidence, "schema_version": "1"}),
                (evidence_path, {**evidence, "schema_version": False}),
            )
            for target, value in invalid:
                with self.subTest(file=target.name, payload=str(value.get("schema_version"))):
                    target.write_text(json.dumps(value), encoding="utf-8")
                    try:
                        with mock.patch(
                            "mixlab.evaluation.inspect_wav_and_digest",
                            side_effect=AssertionError("WAV opened")
                        ) as inspect:
                            with self.assertRaisesRegex(ValueError, "identity|schema|manifest"):
                                verify_pack(self.pack)
                            inspect.assert_not_called()
                    finally:
                        target.write_bytes(receipt_raw if target == receipt_path
                                           else evidence_raw)
        finally:
            receipt_path.write_bytes(receipt_raw)
            evidence_path.write_bytes(evidence_raw)

    def test_pack_trials_and_render_lists_obey_registered_pair_budget(self):
        # Library ingest admits at most 10 pairs; the renderer emits up to
        # 3 blind candidates + baseline per pair. Prevent thousands of
        # individually-hashed frozen WAVs from a forged small JSON envelope.
        answer_path = self.pack / "private" / "answer-key.json"
        evidence_path = self.pack / "private" / "evidence.json"
        answers_raw, evidence_raw = answer_path.read_bytes(), evidence_path.read_bytes()
        try:
            answers = json.loads(answers_raw)
            evidence = json.loads(evidence_raw)
            oversize = [
                (answer_path, answers * 11),  # >30 trial records
                (evidence_path, {**evidence,
                                 "renders": evidence["renders"] * 11}),  # >40
            ]
            for target, fake in oversize:
                with self.subTest(target=target.name):
                    target.write_text(json.dumps(fake), encoding="utf-8")
                    try:
                        with mock.patch(
                            "mixlab.evaluation.inspect_wav_and_digest",
                            side_effect=AssertionError("WAV was opened")
                        ) as inspect:
                            with self.assertRaisesRegex(ValueError, "budget"):
                                verify_pack(self.pack)
                            inspect.assert_not_called()
                    finally:
                        target.write_bytes(answers_raw if target == answer_path
                                           else evidence_raw)
        finally:
            answer_path.write_bytes(answers_raw)
            evidence_path.write_bytes(evidence_raw)

    def test_real_synthetic_frozen_pack_still_verifies(self):
        _receipt, _evidence, trials = verify_pack(self.pack)
        self.assertIn("trial-001", trials)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_replaced_review_wav_fifo_fails_before_blocking(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            os.mkfifo(self.wav)
            started = time.monotonic()
            with self.assertRaises(ValueError):
                verify_pack(self.pack)
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            self.wav.unlink()
            original.rename(self.wav)

    def test_replaced_review_wav_symlink_rejected(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            self.wav.symlink_to(original.name)
            with self.assertRaisesRegex(ValueError, "regular PCM16 WAV"):
                verify_pack(self.pack)
        finally:
            self.wav.unlink()
            original.rename(self.wav)

    def test_oversize_sparse_review_wav_refused(self):
        original = self.wav.with_suffix(".original")
        self.wav.rename(original)
        try:
            with self.wav.open("wb") as stream:
                stream.truncate(MAX_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "32 MiB"):
                verify_pack(self.pack)
        finally:
            self.wav.unlink()
            original.rename(self.wav)


if __name__ == "__main__":
    unittest.main()
