"""Real PCM-backed holdout disjointness and frozen-study integrity QA.

Creates only original short procedural WAV files in isolated temp directories.
No licensed recordings, listener data or external services are used.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

from mixlab.quality.holdout_isolation import audit_holdout_isolation


def _canonical_sha(data):
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _wav(path, identity):
    # Exactly 0.5 seconds at 8k mono PCM16, enough for a 1-beat/120 BPM
    # original short prototype recipe. Unique frequencies for every source.
    frequency = 97 + 17 * identity
    samples = b"".join(struct.pack("<h", round(
        3700 * math.sin(2 * math.pi * frequency * n / 8000)
    )) for n in range(4000))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        writer.writeframes(samples)


class PrivateHoldoutIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="mixlab-holdout-private-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dev_dir = self.root / "private-dev"
        self.eva_dir = self.root / "private-evaluation"
        self.dev_dir.mkdir()
        self.eva_dir.mkdir()
        self.dev_file = self.dev_dir / "library.json"
        self.eva_file = self.eva_dir / "library.json"
        self.study_file = self.root / "study.json"

        self.dev = {"schema_version": 1, "purpose": "private-development",
                    "tracks": [], "pairs": []}
        self.eva = {"schema_version": 1, "purpose": "blind-evaluation",
                    "tracks": [], "pairs": []}

        for i in range(2):
            self.dev["tracks"].append(self._track("dev", i, 1 + i))
        self.dev["pairs"].append({"id": "dev-pair-01", "a": "dev-00",
                                   "b": "dev-01", "bpm": 120, "beats": 1})

        for i in range(10):
            self.eva["tracks"].append(self._track("eva", i, 10 + i))
        families = ("bass_swap", "echo_exit", "hard_cut", "bass_swap", "echo_exit")
        pairs = []
        for i in range(5):
            a, b = self.eva["tracks"][2*i], self.eva["tracks"][2*i + 1]
            self.eva["pairs"].append({
                "id": f"eval-pair-{i+1:02d}", "a": a["id"], "b": b["id"],
                "bpm": 120, "beats": 1,
            })
            pairs.append({
                "pair_id": f"pair-{i+1:02d}", "a": a["id"], "b": b["id"],
                "a_sha256": a["sha256"], "b_sha256": b["sha256"],
                "a_bpm": 120.0, "b_bpm": 120.0,
                "renderable_without_stretch": True,
                "candidate_family": families[i],
            })
        self.study = {
            "schema_version": 1, "kind": "mixlab-frozen-pair-study",
            "protocol": {"minimum_listeners": 3},
            "max_track_uses": 2, "pairs": pairs,
        }
        self.freeze()
        self.persist()

    def _track(self, group, n, audio_id):
        directory = self.dev_dir if group == "dev" else self.eva_dir
        name = f"clip-{n:02d}.wav"
        wav = directory / name
        _wav(wav, audio_id)
        return {
            "id": f"{group}-{n:02d}", "path": name,
            "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
            "bpm": 120, "rights": "synthetic",
            "provenance": "original procedural unittest tone",
            "partition": "development" if group == "dev" else "evaluation",
            "recording_id": f"synthetic-recording-{audio_id:03d}",
        }

    def freeze(self):
        self.study.pop("study_id", None)
        self.pinned = _canonical_sha(self.study)
        self.study["study_id"] = self.pinned

    def persist(self):
        _write_json(self.dev_file, self.dev)
        _write_json(self.eva_file, self.eva)
        _write_json(self.study_file, self.study)

    def audit(self, pin=None):
        self.persist()
        return audit_holdout_isolation(
            self.dev_file, self.eva_file, self.study_file,
            self.pinned if pin is None else pin,
        )

    def rejected(self):
        with self.assertRaises(ValueError) as error:
            self.audit()
        for private in (str(self.root), "dev-00", "eva-00",
                        self.pinned, "synthetic-recording-"):
            self.assertNotIn(private, str(error.exception))

    def test_valid_pinned_ten_source_five_pair_study_isolated(self):
        before = [p.read_bytes() for p in (
            self.dev_dir / "clip-00.wav", self.eva_dir / "clip-00.wav")]
        report = self.audit()
        self.assertEqual(report["development_track_count"], 2)
        self.assertEqual(report["evaluation_track_count"], 10)
        self.assertEqual(report["frozen_pair_count"], 5)
        self.assertTrue(report["development_evaluation_source_identity_separate"])
        self.assertTrue(report["evaluation_sources_match_externally_pinned_study"])
        for key in ("source_rights_independently_authenticated",
                    "recording_lineage_independently_authenticated",
                    "human_preference_proven", "milestone_pass"):
            self.assertIs(report[key], False)
        dumped = json.dumps(report, sort_keys=True)
        for secret in (str(self.root), self.pinned, "dev-00", "eva-00",
                       "synthetic-recording-", "clip-00.wav"):
            self.assertNotIn(secret, dumped)
        self.assertEqual([p.read_bytes() for p in (
            self.dev_dir / "clip-00.wav", self.eva_dir / "clip-00.wav")], before)

    def test_exact_wav_reused_across_libraries_fails(self):
        wav = self.dev_dir / "clip-00.wav"
        shutil.copyfile(self.eva_dir / "clip-00.wav", wav)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(wav.read_bytes()).hexdigest()
        self.rejected()

    def test_different_wav_checksum_with_identical_decoded_pcm_fails(self):
        wav = self.dev_dir / "clip-00.wav"
        wav.write_bytes((self.eva_dir / "clip-00.wav").read_bytes() + b"trailer")
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(wav.read_bytes()).hexdigest()
        self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                            self.eva["tracks"][0]["sha256"])
        self.rejected()

    def test_different_remaster_pcm_with_same_recording_identity_fails(self):
        self.dev["tracks"][0]["recording_id"] = self.eva["tracks"][0]["recording_id"]
        self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                            self.eva["tracks"][0]["sha256"])
        self.rejected()

    def test_same_source_identifier_even_with_distinct_pcm_fails(self):
        self.dev["tracks"][0]["id"] = "eva-00"
        self.dev["pairs"][0]["a"] = "eva-00"
        self.rejected()

    def test_reused_recording_inside_evaluation_is_not_independent(self):
        self.eva["tracks"][1]["recording_id"] = self.eva["tracks"][0]["recording_id"]
        self.rejected()

    def test_frozen_study_forged_source_sha_is_refused_even_if_rehashed(self):
        self.study["pairs"][0]["a_sha256"] = "a" * 64
        self.freeze()
        self.rejected()

    def test_frozen_study_forged_bpm_is_refused_even_if_rehashed(self):
        self.study["pairs"][0]["a_bpm"] = 125.0
        self.study["pairs"][0]["b_bpm"] = 125.0
        self.freeze()
        self.rejected()

    def test_manifest_swapped_pair_direction_is_not_the_frozen_recipe(self):
        self.eva["pairs"][0]["a"], self.eva["pairs"][0]["b"] = (
            self.eva["pairs"][0]["b"], self.eva["pairs"][0]["a"])
        self.rejected()

    def test_evaluation_manifest_must_not_include_unselected_track(self):
        self.eva["tracks"].append(self._track("eva", 10, 88))
        self.rejected()

    def test_missing_partition_cannot_be_treated_as_holdout_proof(self):
        for row in self.dev["tracks"]:
            row.pop("partition")
        self.rejected()

    def test_rights_field_is_required_but_not_authenticated(self):
        self.eva["tracks"][0]["rights"] = "unknown"
        self.rejected()

    def test_external_study_pin_is_mandatory(self):
        with self.assertRaises(ValueError):
            self.audit(pin="0" * 64)
        with self.assertRaises(ValueError):
            self.audit(pin="secret")

    def test_malformed_manifest_and_study_rejected_without_private_details(self):
        self.persist()
        self.dev_file.write_text('{"schema_version":1,"tracks":[], "pairs":[]}',
                                 encoding="utf-8")
        with self.assertRaises(ValueError) as e:
            audit_holdout_isolation(self.dev_file, self.eva_file,
                                    self.study_file, self.pinned)
        self.assertNotIn(str(self.root), str(e.exception))

    def test_cli_success_never_reveals_source_names_or_identity(self):
        self.persist()
        result = subprocess.run([
            sys.executable, "-m", "mixlab.quality.holdout_isolation",
            str(self.dev_file), str(self.eva_file), str(self.study_file),
            "--expected-study-id", self.pinned,
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIs(data["milestone_pass"], False)
        for secret in (str(self.root), self.pinned,
                       "synthetic-recording-", "eva-00", "dev-00"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_cli_bad_pin_and_unknown_option_redact_every_private_path(self):
        self.persist()
        args = [sys.executable, "-m", "mixlab.quality.holdout_isolation",
                str(self.dev_file), str(self.eva_file), str(self.study_file)]
        for extra in (["--expected-study-id", "0" * 64],
                      ["--expected-study-id", self.pinned,
                       "--SECRET_PRIVATE_REVIEWER_PATH"]):
            with self.subTest(extra=extra[-1]):
                result = subprocess.run(args + extra, capture_output=True,
                                        text=True, timeout=15)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                for secret in (str(self.root), self.pinned,
                               "SECRET_PRIVATE_REVIEWER_PATH", "eva-00"):
                    self.assertNotIn(secret, result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
