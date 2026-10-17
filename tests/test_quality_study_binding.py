"""Synthetic end-to-end tests of the standalone frozen-study/pack metadata QA.

No permitted/real music, listener identities, sources or services are accessed.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.evaluation import verify_pack
from mixlab.quality.study_binding import verify_study_pack_binding


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class FrozenStudyBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mixlab-binding-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pack = self.root / "pack"
        self.review = self.pack / "review"
        self.private = self.pack / "private"
        self.private.mkdir(parents=True)
        self.review.mkdir()
        self.study = self.root / "study.json"

        pairs = []
        keys = []
        renders = []
        for i in range(1, 6):
            number = f"{i:02d}"
            left = hashlib.sha256(f"source-a-{number}".encode()).hexdigest()
            right = hashlib.sha256(f"source-b-{number}".encode()).hexdigest()
            family = ("bass_swap", "echo_exit", "hard_cut")[(i - 1) % 3]
            pairs.append({"pair_id": f"pair-{number}", "a": f"track-{number}-a",
                          "b": f"track-{number}-b", "a_sha256": left,
                          "b_sha256": right, "a_bpm": 120.0, "b_bpm": 120.0,
                          "renderable_without_stretch": True,
                          "candidate_family": family})
            trial = f"trial-{i:03d}"
            pair = f"synthetic-alignment-{number}"
            keys.append({"trial": trial, "pair": pair,
                         "A": "baseline" if i % 2 else family,
                         "B": family if i % 2 else "baseline"})
            for label in ("A", "B"):
                f = keys[-1][label]
                wav = self.review / f"{trial}-{label}.wav"
                # 0.1 sec original procedural mono PCM16, different A and B.
                with wave.open(str(wav), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(8000)
                    stream.writeframes(b"".join(struct.pack("<h", int(
                        2500 * math.sin(2 * math.pi * (90 + 17 * i + (label == "B") * 11) * k / 8000
                    ))) for k in range(800)))
                renders.append({"pair": pair, "study_pair": f"pair-{number}",
                                "family": f,
                                "source_hashes": [left, right],
                                "recipe": {"family": f, "bpm": 120.0, "beats": 4,
                                           "a_bpm": 120.0, "b_bpm": 120.0},
                                "output_sha256": hashlib.sha256(wav.read_bytes()).hexdigest()})

        document = {"schema_version": 1, "kind": "mixlab-frozen-pair-study",
                    "protocol": {"minimum_listeners": 3},
                    "max_track_uses": 2, "pairs": pairs}
        self.pinned = _canonical_sha(document)
        document["study_id"] = self.pinned
        _write_json(self.study, document)
        manifest_sha = hashlib.sha256(b"original-synthetic-manifest").hexdigest()
        identity = {"manifest": manifest_sha, "answers": keys,
                    "outputs": [r["output_sha256"] for r in renders]}
        pack_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        _write_json(self.private / "answer-key.json", keys)
        _write_json(self.private / "evidence.json", {
            "schema_version": 1, "study_id": self.pinned, "manifest_sha256": manifest_sha,
            "renders": renders, "pack_id": pack_id,
        })
        _write_json(self.pack / "receipt.json", {
            "schema_version": 1, "study_id": self.pinned, "manifest_sha256": manifest_sha,
            "pack_id": pack_id, "trial_count": len(keys), "render_count": len(renders),
            "status": "rendered-not-listener-validated",
        })
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)

    def check(self):
        return verify_study_pack_binding(self.study, self.pack, self.pinned)

    def edit(self, filename, mutate):
        path = self.pack / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        _write_json(path, data)

    def test_valid_five_pair_study_is_bound_to_actual_pcm_receipts(self):
        result = self.check()
        self.assertEqual(result["trial_count"], 5)
        self.assertTrue(result["study_pack_metadata_consistent_with_pinned_id"])
        self.assertFalse(result["source_permissions_independently_authenticated"])
        self.assertFalse(result["actual_source_audio_authenticated_by_this_gate"])
        self.assertFalse(result["human_preference_proven"])
        self.assertFalse(result["milestone_pass"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_forging_both_study_ids_is_detected_even_if_pack_id_stays_valid(self):
        for filename in ("receipt.json", "private/evidence.json"):
            self.edit(filename, lambda doc: doc.__setitem__("study_id", "f" * 64))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_forged_source_sha_provenance_outside_pack_id_is_detected(self):
        self.edit("private/evidence.json",
                  lambda doc: doc["renders"][0]["source_hashes"].__setitem__(0, "0" * 64))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_study_pair_reassignment_outside_pack_id_is_detected(self):
        self.edit("private/evidence.json",
                  lambda doc: doc["renders"][0].__setitem__("study_pair", "pair-05"))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_forged_effective_render_tempo_mismatch_detected(self):
        self.edit("private/evidence.json", lambda doc:
                  doc["renders"][0]["recipe"].__setitem__("bpm", 91.0))
        # The old pack id covers WAV bytes and answers, but NOT this recipe
        # claim, so a genuine populated pack can remain internally valid.
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_forged_render_beats_types_and_range_detected(self):
        original = (self.private / "evidence.json").read_bytes()
        for beats in (True, 0, 4.0, 65, "4", None):
            with self.subTest(beats=beats):
                (self.private / "evidence.json").write_bytes(original)
                self.edit("private/evidence.json", lambda doc:
                          doc["renders"][0]["recipe"].__setitem__("beats", beats))
                self.assertEqual(len(verify_pack(self.pack)[2]), 5)
                with self.assertRaisesRegex(ValueError, "do not match"):
                    self.check()

    def test_render_recipe_bpm_forgery_outside_pack_id_is_detected(self):
        self.edit("private/evidence.json",
                  lambda doc: doc["renders"][0]["recipe"].__setitem__("a_bpm", 121.0))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_study_change_with_rehashed_internal_id_still_fails_pinned_external_id(self):
        document = json.loads(self.study.read_text(encoding="utf-8"))
        document["pairs"][0]["a_sha256"] = "0" * 64
        document.pop("study_id")
        document["study_id"] = _canonical_sha(document)
        _write_json(self.study, document)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_wrong_external_id_refused_on_unchanged_real_pack(self):
        with self.assertRaisesRegex(ValueError, "do not match"):
            verify_study_pack_binding(self.study, self.pack, "f" * 64)
        with self.assertRaisesRegex(ValueError, "do not match"):
            verify_study_pack_binding(self.study, self.pack, "not-a-sha")

    def test_pcm_mutation_remains_blocked_by_original_pack_admission(self):
        audio = self.review / "trial-001-A.wav"
        with audio.open("ab") as stream:
            stream.write(b"\x01")
        with self.assertRaises(ValueError):
            self.check()

    def test_private_cli_does_not_echo_paths_on_invalid_study(self):
        missing = self.root / "SECRET_STUDY_PATH" / "unknown.json"
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.study_binding",
            str(missing), str(self.pack), "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertNotIn("SECRET_STUDY_PATH", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_private_cli_success_discloses_only_anonymous_gate_result(self):
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.study_binding",
            str(self.study), str(self.pack), "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["study_pack_metadata_consistent_with_pinned_id"])
        self.assertNotIn(self.pinned, result.stdout)
        self.assertNotIn(str(self.root), result.stdout)


    def test_hash_consistent_but_nonstr_candidate_type_is_rejected_cleanly(self):
        # Even a self-consistently hashed malformed study must raise an
        # ordinary validation error, not an unhandled unhashable-list TypeError.
        from mixlab.quality.study_binding import _verified_study
        doc = json.loads(self.study.read_text(encoding="utf-8"))
        doc["pairs"][0]["candidate_family"] = []
        doc.pop("study_id")
        recalc = _canonical_sha(doc)
        doc["study_id"] = recalc
        _write_json(self.study, doc)
        with self.assertRaisesRegex(ValueError, "do not match"):
            _verified_study(self.study, recalc)

    def test_actual_pack_one_sided_study_id_replacement_is_rejected(self):
        self.edit("receipt.json", lambda doc: doc.__setitem__("study_id", "f" * 64))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()

    def test_actual_pack_recipe_family_mismatch_is_rejected(self):
        self.edit("private/evidence.json", lambda doc:
                  doc["renders"][0]["recipe"].__setitem__("family", "echo_exit"))
        self.assertEqual(len(verify_pack(self.pack)[2]), 5)
        with self.assertRaisesRegex(ValueError, "do not match"):
            self.check()



    def test_untrusted_unknown_option_does_not_expose_private_flag_or_path(self):
        secret = "--PRIVATE_REVIEWER_SOURCE_KEY_5688"
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.study_binding",
            str(self.study), str(self.pack), "--expected-study-id", self.pinned,
            secret, str(self.root / "PRIVATE_AUDIO_OPERATOR_PATH"),
        ], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid arguments", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertNotIn("PRIVATE_AUDIO_OPERATOR_PATH", result.stdout + result.stderr)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_required_flag_has_static_nonsecret_error(self):
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.study_binding",
            str(self.study), str(self.pack),
        ], capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid arguments", result.stderr)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)



    def test_wrong_public_study_id_refused_before_private_pcm_scan(self):
        from unittest import mock
        self.edit("receipt.json", lambda doc: doc.__setitem__("study_id", "f" * 64))
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        side_effect=AssertionError("private PCM scanned")) as scanner:
            with self.assertRaisesRegex(ValueError, "do not match"):
                self.check()
            scanner.assert_not_called()

    def test_wrong_private_study_id_refused_before_private_pcm_scan(self):
        from unittest import mock
        self.edit("private/evidence.json",
                  lambda doc: doc.__setitem__("study_id", "f" * 64))
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        side_effect=AssertionError("private PCM scanned")) as scanner:
            with self.assertRaisesRegex(ValueError, "do not match"):
                self.check()
            scanner.assert_not_called()

    def test_correct_study_id_reaches_one_real_pcm_verification(self):
        from unittest import mock
        from mixlab.evaluation import verify_pack as original
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        wraps=original) as scanner:
            self.assertTrue(self.check()["study_pack_metadata_consistent_with_pinned_id"])
            scanner.assert_called_once()



    def _assert_bad_rehashed_study(self, mutation):
        # Even a newly calculated SHA-256 supplied as the expected ID cannot
        # turn an invalid study protocol into a valid frozen blind experiment.
        from mixlab.quality.study_binding import _verified_study
        doc = json.loads(self.study.read_text(encoding="utf-8"))
        mutation(doc)
        doc.pop("study_id")
        new_id = _canonical_sha(doc)
        doc["study_id"] = new_id
        _write_json(self.study, doc)
        with self.assertRaisesRegex(ValueError, "do not match"):
            _verified_study(self.study, new_id)

    def test_rehashed_all_same_candidate_family_fails_protocol(self):
        self._assert_bad_rehashed_study(lambda d: [
            p.__setitem__("candidate_family", "bass_swap") for p in d["pairs"]])

    def test_rehashed_track_use_above_frozen_limit_fails_protocol(self):
        def bad(doc):
            doc["max_track_uses"] = 1
            doc["pairs"][1]["a"] = doc["pairs"][0]["a"]
            doc["pairs"][1]["a_sha256"] = doc["pairs"][0]["a_sha256"]
        self._assert_bad_rehashed_study(bad)

    def test_rehashed_bool_or_missing_reuse_limit_rejected(self):
        for invalid in (None, False, True, 0, 2.0, 5):
            with self.subTest(value=invalid):
                doc = json.loads(self.study.read_text(encoding="utf-8"))
                doc["max_track_uses"] = invalid
                from mixlab.quality.study_binding import _verified_study
                doc.pop("study_id")
                candidate_id = _canonical_sha(doc)
                doc["study_id"] = candidate_id
                _write_json(self.study, doc)
                with self.assertRaisesRegex(ValueError, "do not match"):
                    _verified_study(self.study, candidate_id)

    def test_rehashed_source_recording_alias_under_new_track_id_rejected(self):
        self._assert_bad_rehashed_study(lambda d:
            d["pairs"][1].__setitem__("a_sha256", d["pairs"][0]["a_sha256"]))

    def test_rehashed_same_track_id_claims_two_different_sources_rejected(self):
        self._assert_bad_rehashed_study(lambda d:
            d["pairs"][1].__setitem__("a", d["pairs"][0]["a"]))

    def test_rehashed_malformed_digest_type_fails_cleanly(self):
        original = self.study.read_bytes()
        for invalid in ([], {}, {"hidden": "source"}, True, None, 9):
            with self.subTest(digest=repr(invalid)):
                self.study.write_bytes(original)
                self._assert_bad_rehashed_study(lambda d:
                    d["pairs"][0].__setitem__("a_sha256", invalid))

    def test_rehashed_unrenderable_pair_never_passes_quality_gate(self):
        self._assert_bad_rehashed_study(lambda d:
            d["pairs"][0].__setitem__("renderable_without_stretch", False))

    def test_rehashed_renderable_flag_must_be_actual_boolean(self):
        self._assert_bad_rehashed_study(lambda d:
            d["pairs"][0].__setitem__("renderable_without_stretch", 1))

    def test_rehashed_unmatched_source_tempo_cannot_claim_renderable(self):
        self._assert_bad_rehashed_study(lambda d:
            d["pairs"][0].__setitem__("b_bpm", 121.0))

    def test_reuse_exactly_at_allowed_limit_is_valid_study_shape(self):
        from mixlab.quality.study_binding import _verified_study
        doc = json.loads(self.study.read_text(encoding="utf-8"))
        doc["pairs"][1]["a"] = doc["pairs"][0]["a"]
        doc["pairs"][1]["a_sha256"] = doc["pairs"][0]["a_sha256"]
        doc.pop("study_id")
        ident = _canonical_sha(doc)
        doc["study_id"] = ident
        _write_json(self.study, doc)
        self.assertEqual(_verified_study(self.study, ident)["max_track_uses"], 2)


    def test_forged_effective_render_bpm_refused_before_private_pcm(self):
        from unittest import mock
        self.edit("private/evidence.json", lambda doc:
                  doc["renders"][0]["recipe"].__setitem__("bpm", 91.0))
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        side_effect=AssertionError("private WAV opened")) as scanner:
            with self.assertRaisesRegex(ValueError, "do not match"):
                self.check()
            scanner.assert_not_called()

    def test_forged_original_source_hash_refused_before_private_pcm(self):
        from unittest import mock
        self.edit("private/evidence.json", lambda doc:
                  doc["renders"][0]["source_hashes"].__setitem__(0, "0" * 64))
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        side_effect=AssertionError("private WAV opened")) as scanner:
            with self.assertRaisesRegex(ValueError, "do not match"):
                self.check()
            scanner.assert_not_called()

    def test_post_pcm_metadata_drift_refused_before_report(self):
        from unittest import mock
        from mixlab.evaluation import verify_pack as original
        def drift(root):
            receipt, evidence, trials = original(root)
            evidence["renders"][0]["recipe"]["bpm"] = 91.0
            return receipt, evidence, trials
        with mock.patch("mixlab.quality.study_binding.verify_pack",
                        side_effect=drift) as scanner:
            with self.assertRaisesRegex(ValueError, "do not match"):
                self.check()
            scanner.assert_called_once()



if __name__ == "__main__":
    unittest.main()
