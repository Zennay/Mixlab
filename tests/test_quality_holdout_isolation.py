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
from unittest import mock
import wave

from mixlab.quality.holdout_isolation import (
    audit_holdout_isolation, _pcm_exact_transform_variants,
)


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


    def test_full_fifty_source_budget_remains_admitted_and_anonymous(self):
        # End-to-end scale at the documented maximum: 40 development tracks,
        # ten externally pinned evaluation tracks, and real PCM for all.
        for i in range(2, 40):
            self.dev["tracks"].append(self._track("dev", i, 100 + i))
        report = self.audit()
        self.assertEqual(report["development_track_count"], 40)
        self.assertEqual(report["evaluation_track_count"], 10)
        self.assertFalse(report["milestone_pass"])


    def _write_max_frame_source(self, count):
        """Write 2M original PCM frames in bounded chunks (no giant buffer)."""
        target = self.dev_dir / "clip-00.wav"
        chunk = b"".join(struct.pack(
            "<h", (i * 37 + 101) % 18000 - 9000
        ) for i in range(8192))
        remaining = count
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            while remaining > 0:
                take = min(remaining, 8192)
                writer.writeframesraw(chunk[:take * 2])
                remaining -= take
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(
            target.read_bytes()).hexdigest()

    def test_exact_two_million_pcm_frames_stream_under_existing_budget(self):
        self._write_max_frame_source(2_000_000)
        self.assertTrue(self.audit()["development_evaluation_source_identity_separate"])

    def test_one_frame_above_source_budget_is_rejected(self):
        self._write_max_frame_source(2_000_001)
        self.rejected()

    def test_fifty_one_sources_fail_closed_even_if_each_manifest_is_valid(self):
        for i in range(2, 41):
            self.dev["tracks"].append(self._track("dev", i, 100 + i))
        self.rejected()

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


    def _gain_variant(self, gain):
        source = self.eva_dir / "clip-00.wav"
        target = self.dev_dir / "clip-00.wav"
        with wave.open(str(source), "rb") as reader:
            samples = struct.unpack("<" + "h" * reader.getnframes(),
                                    reader.readframes(reader.getnframes()))
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(b"".join(struct.pack("<h", int(value * gain))
                                        for value in samples))
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()

    def test_inverse_and_exact_gain_edited_copies_are_contamination(self):
        for factor in (-1, 2, -2):
            with self.subTest(gain=factor):
                self._gain_variant(factor)
                self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                                    self.eva["tracks"][0]["sha256"])
                self.rejected()

    def test_nonexact_gain_does_not_claim_an_identical_pcm_excerpt(self):
        # Not acoustic similarity; 1.5x gain is deliberately not represented
        # by the exact integer-transform family and must not become a false
        # asserted clip reuse on distinct PCM bytes.
        self._gain_variant(1.5)
        self.assertTrue(self.audit()["development_evaluation_source_identity_separate"])

    def _to_stereo(self, path):
        with wave.open(str(path), "rb") as reader:
            mono = struct.unpack("<" + "h" * reader.getnframes(),
                                 reader.readframes(reader.getnframes()))
        frames = b"".join(struct.pack(
            "<hh", value, value // 3 + (30 if i % 2 else -30))
            for i, value in enumerate(mono))
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(frames)

    def _prepare_stereo_pair(self):
        for group, directory in ((self.dev, self.dev_dir),
                                 (self.eva, self.eva_dir)):
            for index in (0, 1):
                path = directory / f"clip-{index:02d}.wav"
                self._to_stereo(path)
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                group["tracks"][index]["sha256"] = sha
                if group is self.eva:
                    self.study["pairs"][0][("a" if index == 0 else "b") + "_sha256"] = sha
        self.freeze()

    def _make_unique_stereo_with_shared_silent_right(self):
        # Deliberately unrelated left-channel melodies, but an all-zero
        # right channel in both sets. Silence is not musical provenance.
        for group, directory in ((self.dev, self.dev_dir),
                                 (self.eva, self.eva_dir)):
            for i in (0, 1):
                path = directory / f"clip-{i:02d}.wav"
                with wave.open(str(path), "rb") as reader:
                    mono = reader.readframes(reader.getnframes())
                stereo = b"".join(struct.pack("<hh", value, 0)
                                  for (value,) in struct.iter_unpack("<h", mono))
                with wave.open(str(path), "wb") as writer:
                    writer.setnchannels(2)
                    writer.setsampwidth(2)
                    writer.setframerate(8000)
                    writer.writeframes(stereo)
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                group["tracks"][i]["sha256"] = sha
                if group is self.eva:
                    self.study["pairs"][0][
                        ("a" if i == 0 else "b") + "_sha256"] = sha
        self.freeze()

    def test_shared_silent_stereo_channel_is_not_source_contamination(self):
        self._make_unique_stereo_with_shared_silent_right()
        report = self.audit()
        self.assertIs(report["development_evaluation_source_identity_separate"], True)
        self.assertIs(report["milestone_pass"], False)

    def test_copy_of_real_audible_channel_rejected_even_with_shared_silence(self):
        self._make_unique_stereo_with_shared_silent_right()
        donor = self.eva_dir / "clip-00.wav"
        receiver = self.dev_dir / "clip-00.wav"
        with wave.open(str(donor), "rb") as reader:
            source = list(struct.iter_unpack(
                "<hh", reader.readframes(reader.getnframes())))
        with wave.open(str(receiver), "rb") as reader:
            original = list(struct.iter_unpack(
                "<hh", reader.readframes(reader.getnframes())))
        edited = b"".join(struct.pack("<hh", donor_l, right)
                          for (donor_l, _), (_, right) in zip(source, original))
        with wave.open(str(receiver), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(edited)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(
            receiver.read_bytes()).hexdigest()
        self.rejected()

    def test_stereo_source_pair_accepts_independent_channels(self):
        self._prepare_stereo_pair()
        self.assertTrue(self.audit()["development_evaluation_source_identity_separate"])

    def test_stereo_channel_swapped_eval_copy_rejected_in_development(self):
        self._prepare_stereo_pair()
        source = self.eva_dir / "clip-00.wav"
        target = self.dev_dir / "clip-00.wav"
        with wave.open(str(source), "rb") as reader:
            frames = reader.readframes(reader.getnframes())
        swapped = b"".join(struct.pack("<hh", right, left)
                           for left, right in struct.iter_unpack("<hh", frames))
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(swapped)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.rejected()


    def test_mono_copy_of_stereo_left_channel_is_not_a_new_recording(self):
        # Evaluation pair 1 is genuine stereo; development stays mono.
        for i in (0, 1):
            original = self.eva_dir / f"clip-{i:02d}.wav"
            self._to_stereo(original)
            sha = hashlib.sha256(original.read_bytes()).hexdigest()
            self.eva["tracks"][i]["sha256"] = sha
            self.study["pairs"][0][("a" if i == 0 else "b") + "_sha256"] = sha
        self.freeze()
        with wave.open(str(self.eva_dir / "clip-00.wav"), "rb") as reader:
            interleaved = reader.readframes(reader.getnframes())
        mono = b"".join(struct.pack("<h", left)
                        for left, right in struct.iter_unpack("<hh", interleaved))
        target = self.dev_dir / "clip-00.wav"
        with wave.open(str(target), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(mono)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.rejected()

    def test_stereo_with_one_copied_channel_and_other_original_is_contamination(self):
        self._prepare_stereo_pair()
        source = self.eva_dir / "clip-00.wav"
        destination = self.dev_dir / "clip-00.wav"
        with wave.open(str(source), "rb") as reader:
            donor = reader.readframes(reader.getnframes())
        with wave.open(str(destination), "rb") as reader:
            previous = reader.readframes(reader.getnframes())
        donor_left = [frame[0] for frame in struct.iter_unpack("<hh", donor)]
        original_right = [frame[1] for frame in struct.iter_unpack("<hh", previous)]
        mixed = b"".join(struct.pack("<hh", left, right)
                         for left, right in zip(donor_left, original_right))
        with wave.open(str(destination), "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(mixed)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(
            destination.read_bytes()).hexdigest()
        self.rejected()

    def test_mono_and_stereo_independent_sources_do_not_trigger_cross_channel(self):
        for i in (0, 1):
            target = self.eva_dir / f"clip-{i:02d}.wav"
            self._to_stereo(target)
            new_sha = hashlib.sha256(target.read_bytes()).hexdigest()
            self.eva["tracks"][i]["sha256"] = new_sha
            self.study["pairs"][0][("a" if i == 0 else "b") + "_sha256"] = new_sha
        self.freeze()
        self.assertTrue(self.audit()["development_evaluation_source_identity_separate"])

    def test_transform_overflow_omits_unrepresentable_signed16_forms(self):
        # -32768 cannot be negated and 16384 cannot be doubled in PCM16.
        raw = struct.pack("<hh", -32768, 16384)
        self.assertEqual(_pcm_exact_transform_variants(raw, 1), {raw})
        with self.assertRaises(ValueError):
            _pcm_exact_transform_variants(b"\x01", 1)

    def test_different_remaster_pcm_with_same_recording_identity_fails(self):
        self.dev["tracks"][0]["recording_id"] = self.eva["tracks"][0]["recording_id"]
        self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                            self.eva["tracks"][0]["sha256"])
        self.rejected()

    def test_same_source_identifier_even_with_distinct_pcm_fails(self):
        self.dev["tracks"][0]["id"] = "eva-00"
        self.dev["pairs"][0]["a"] = "eva-00"
        self.rejected()


    def _replace_wav_with_embedded(self, destination, source, prefix_frames=4000):
        """Create a distinct longer WAV containing a copied 0.5s PCM crop."""
        with wave.open(str(source), "rb") as reader:
            shared = reader.readframes(reader.getnframes())
        with wave.open(str(destination), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(8000)
            writer.writeframes(b"\x00" * (prefix_frames * 2) + shared + b"\x00" * 8000)


    def test_quarter_position_hidden_crop_is_detected_in_two_long_recordings(self):
        # The reused 0.5s audible clip is not at start/middle/end of EITHER
        # 5-second source. With only three anchors this passed incorrectly.
        with wave.open(str(self.eva_dir / "clip-00.wav"), "rb") as reader:
            shared = reader.readframes(reader.getnframes())
        frames = 40000
        for fraction in (0.25, 0.75):
            with self.subTest(source_quartile=fraction):
                beginning = round((frames - 1600) * fraction) - 100
                for directory, records, slope in (
                        (self.dev_dir, self.dev, 37),
                        (self.eva_dir, self.eva, 83)):
                    target = directory / "clip-00.wav"
                    carrier = b"".join(struct.pack(
                        "<h", ((frame * slope + (23 if records is self.dev else 71))
                               % 16000) - 8000
                    ) for frame in range(frames))
                    body = (carrier[:beginning * 2] + shared
                            + carrier[(beginning + 4000) * 2:])
                    with wave.open(str(target), "wb") as output:
                        output.setnchannels(1)
                        output.setsampwidth(2)
                        output.setframerate(8000)
                        output.writeframes(body)
                    records["tracks"][0]["sha256"] = hashlib.sha256(
                        target.read_bytes()).hexdigest()
                self.study["pairs"][0]["a_sha256"] = self.eva["tracks"][0]["sha256"]
                self.freeze()
                self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                                    self.eva["tracks"][0]["sha256"])
                self.rejected()

    def test_full_hashes_and_recording_ids_miss_embedded_same_recording_crop(self):
        # Both ordinary file and decoded-whole-file digests differ; no shared
        # recording_id is claimed. The new streaming anchor screen must catch
        # the exact audible section embedded after a long silent prefix.
        original = self.eva_dir / "clip-00.wav"
        target = self.dev_dir / "clip-00.wav"
        self._replace_wav_with_embedded(target, original)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertNotEqual(self.dev["tracks"][0]["sha256"],
                            self.eva["tracks"][0]["sha256"])
        self.assertNotEqual(self.dev["tracks"][0]["recording_id"],
                            self.eva["tracks"][0]["recording_id"])
        self.rejected()


    def test_reused_pcm_crossing_a_stream_block_boundary_is_detected(self):
        # Auditable prefix length: playback PCM starts 8 frames before the
        # 32,768-frame streaming boundary and continues after the boundary.
        source = self.eva_dir / "clip-00.wav"
        target = self.dev_dir / "clip-00.wav"
        self._replace_wav_with_embedded(target, source, prefix_frames=32760)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.rejected()

    def test_mutation_after_excerpt_preflight_fails_on_final_source_rescan(self):
        from mixlab.quality import holdout_isolation
        self.persist()
        original_screen = holdout_isolation._exact_pcm_excerpt_overlap

        def damage_after_pass(dev, eva):
            outcome = original_screen(dev, eva)
            self.assertFalse(outcome)
            (self.dev_dir / "clip-00.wav").write_bytes(b"source changed")
            return outcome

        with mock.patch.object(holdout_isolation, "_exact_pcm_excerpt_overlap",
                               side_effect=damage_after_pass):
            with self.assertRaises(ValueError) as error:
                holdout_isolation.audit_holdout_isolation(
                    self.dev_file, self.eva_file, self.study_file, self.pinned)
        self.assertNotIn(str(self.root), str(error.exception))

    def test_frozen_evaluation_cannot_use_an_embedded_copy_as_new_track(self):
        target = self.eva_dir / "clip-01.wav"
        self._replace_wav_with_embedded(target, self.eva_dir / "clip-00.wav")
        self.eva["tracks"][1]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.study["pairs"][0]["b_sha256"] = self.eva["tracks"][1]["sha256"]
        self.freeze()
        self.rejected()

    def test_shared_silence_alone_does_not_trigger_a_musical_leak(self):
        target = self.dev_dir / "clip-00.wav"
        with wave.open(str(target), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\x00" * 16000)
        self.dev["tracks"][0]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertTrue(self.audit()["development_evaluation_source_identity_separate"])

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
