"""ML-03: cached analysis integrity must include provenance semantics.

Uses generated PCM silence only, without third-party music or model access.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave

from mixlab.analysis import EnergyOnsetProvider, ManualProvider, analyze_cached


class ProviderProvenanceCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mixlab-provider-receipt-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "synth.wav"
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)

    def _warm(self, provider, folder):
        directory = self.root / folder
        expected = analyze_cached(self.source, directory, provider)
        cache = list(directory.glob("*.json"))
        self.assertEqual(len(cache), 1)
        return directory, cache[0], expected, json.loads(cache[0].read_text())

    def _corrupt_with_valid_digest(self, original, entry, field, replacement):
        forged = json.loads(json.dumps(original))
        forged["analysis"][field] = replacement
        raw = json.dumps(forged["analysis"], sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        forged["analysis_sha256"] = hashlib.sha256(raw).hexdigest()
        entry.write_text(json.dumps(forged), encoding="utf-8")

    def test_manual_receipt_cannot_impersonate_measured_or_other_annotations(self):
        provider = ManualProvider(120, first_beat=0, annotator="synthetic")
        directory, entry, expected, pristine = self._warm(provider, "manual")
        self.assertEqual(expected, analyze_cached(self.source, directory, provider))
        changes = (
            ("provider", "energy-onset"),
            ("timing_source", "measured-heuristic"),
            ("key_source", "measured"),
            ("tempo_confidence", 0.8),
            ("bpm", 121),
            ("beats_seconds", []),
            ("downbeats_seconds", [0.0]),
            ("phrase_starts_seconds", [0.0]),
            ("key", "C major"),
            ("energy", [[0.0, 0.1]]),
            ("warnings", ["automatically measured"]),
        )
        for field, value in changes:
            with self.subTest(field=field):
                self._corrupt_with_valid_digest(pristine, entry, field, value)
                with self.assertRaisesRegex(ValueError, "provenance/config"):
                    analyze_cached(self.source, directory, provider)

    def test_versioned_third_party_provider_cache_remains_supported(self):
        class ThirdPartyProvider:
            version = "custom-v1"

            def analyze(self, path):
                manual = ManualProvider(120, annotator="synthetic")
                return replace(manual.analyze(path), provider="external-custom",
                               provider_version=self.version)

        custom = ThirdPartyProvider()
        directory, entry, expected, _ = self._warm(custom, "third-party")
        self.assertEqual(expected["provider"], "external-custom")
        self.assertEqual(expected, analyze_cached(self.source, directory, custom))
        self.assertTrue(entry.exists())

    def test_manual_config_version_cannot_be_repurposed_after_creation(self):
        provider = ManualProvider(120, first_beat=0, downbeats=(0, 0.5),
                                  phrases=(0,), key="A minor",
                                  annotator="synthetic")
        original_version = provider.version
        directory, entry, first, _ = self._warm(provider, "frozen-manual")
        self.assertEqual(first, analyze_cached(self.source, directory, provider))
        for key, value in (("bpm", 121), ("first_beat", 0.5),
                           ("downbeats", (0,)), ("key", "C major"),
                           ("annotator", "different")):
            with self.subTest(key=key), self.assertRaises(TypeError):
                provider.config[key] = value
        self.assertEqual(provider.version, original_version)
        self.assertEqual(provider.config["bpm"], 120)
        self.assertEqual(first, analyze_cached(self.source, directory, provider))
        self.assertTrue(entry.is_file())

    def test_manual_constructor_rejects_bad_types_before_audio_io(self):
        invalid = (
            {"key": []}, {"key": {"C": "major"}},
            {"downbeats": None}, {"downbeats": "0,1"},
            {"downbeats": {"bad": 1}}, {"downbeats": (True,)},
            {"downbeats": (float("nan"),)}, {"downbeats": (float("inf"),)},
            {"downbeats": (-1,)}, {"downbeats": (0, 0)},
            {"downbeats": (0.5, 0)}, {"downbeats": (0.333,)},
            {"phrases": None}, {"phrases": "0"},
            {"phrases": (0.5,)}, {"phrases": (True,)},
            {"phrases": (0, 0)}, {"phrases": (float("nan"),)},
            {"downbeats": [i * 0.5 for i in range(10001)]},
        )
        from unittest import mock
        with mock.patch("mixlab.analysis.inspect_wav",
                        side_effect=AssertionError("audio accessed")) as audio:
            for kwargs in invalid:
                with self.subTest(kwargs=str(kwargs)[:70]):
                    with self.assertRaises(ValueError):
                        ManualProvider(120, annotator="synthetic", **kwargs)
            audio.assert_not_called()

    def test_measured_receipt_cannot_claim_manual_or_fabricated_features(self):
        provider = EnergyOnsetProvider()
        directory, entry, expected, pristine = self._warm(provider, "measured")
        self.assertEqual(expected, analyze_cached(self.source, directory, provider))
        changes = (
            ("provider", "manual"),
            ("timing_source", "manual"),
            ("key_source", "manual"),
            ("key", "C major"),
            ("downbeats_seconds", [0.0]),
            ("phrase_starts_seconds", [0.0]),
            ("warnings", []),
            ("warnings", ["insufficient rhythmic evidence"]),
            ("warnings", ["tempo octave ambiguity; verify beatgrid before rendering", "key is automatically inferred"]),
        )
        for field, value in changes:
            with self.subTest(field=field):
                self._corrupt_with_valid_digest(pristine, entry, field, value)
                with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    analyze_cached(self.source, directory, provider)


if __name__ == "__main__":
    unittest.main()
