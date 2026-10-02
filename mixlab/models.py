"""Canonical experiment records. Tempo and alignment are supplied by humans."""

from dataclasses import asdict, dataclass, field
import math
from typing import Any


RIGHTS_STATUSES = ("unknown", "owned", "synthetic", "licensed", "user-permitted", "public-domain", "public_domain")
FAMILY_NAMES = ("baseline", "bass_swap", "echo_exit", "hard_cut")


@dataclass(frozen=True)
class Track:
    id: str
    path: str
    title: str = ""
    bpm: float | None = None
    downbeat_seconds: float | None = None
    rights_status: str = "unknown"
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id or not self.path:
            raise ValueError("Track id and path are required")
        if self.rights_status not in RIGHTS_STATUSES:
            raise ValueError("Unsupported rights_status")
        if self.bpm is not None and (not math.isfinite(self.bpm) or self.bpm <= 0):
            raise ValueError("Track bpm must be finite and positive")
        if self.downbeat_seconds is not None and (
            not math.isfinite(self.downbeat_seconds) or self.downbeat_seconds < 0
        ):
            raise ValueError("downbeat_seconds must be finite and nonnegative")


@dataclass(frozen=True)
class Segment:
    track_id: str
    start_seconds: float
    beats: int
    alignment_source: str = "manual"

    def __post_init__(self):
        if not self.track_id:
            raise ValueError("Segment requires a track_id")
        if not math.isfinite(self.start_seconds) or self.start_seconds < 0:
            raise ValueError("Segment start must be finite and nonnegative")
        if isinstance(self.beats, bool) or not isinstance(self.beats, int) or self.beats < 1:
            raise ValueError("Segment beats must be a positive integer")
        if self.alignment_source != "manual":
            raise ValueError("Only manual alignment is implemented")


@dataclass(frozen=True)
class Recipe:
    family: str = "baseline"
    bpm: float = 120.0
    beats: int = 8
    a_start: float = 0.0
    b_start: float = 0.0
    gain_db: float = -6.0
    a_bpm: float | None = None
    b_bpm: float | None = None

    def __post_init__(self):
        if self.family not in FAMILY_NAMES:
            raise ValueError(f"family must be one of {FAMILY_NAMES}")
        if not math.isfinite(self.bpm) or not 30 <= self.bpm <= 300:
            raise ValueError("bpm must be between 30 and 300")
        if isinstance(self.beats, bool) or not isinstance(self.beats, int) or not 1 <= self.beats <= 64:
            raise ValueError("beats must be an integer from 1 to 64")
        for label, start in (("a_start", self.a_start), ("b_start", self.b_start)):
            if not math.isfinite(start) or start < 0:
                raise ValueError(f"{label} must be finite and nonnegative")
        if not math.isfinite(self.gain_db) or not -60 <= self.gain_db <= 0:
            raise ValueError("gain_db must be between -60 and 0")
        for tempo in (self.a_bpm, self.b_bpm):
            if tempo is not None and (not math.isfinite(tempo) or abs(tempo - self.bpm) > 1e-9):
                raise ValueError("Source tempos must match recipe bpm; time stretching is not implemented")
        if self.beats * 60 / self.bpm > 120:
            raise ValueError("Render duration cannot exceed 120 seconds")


@dataclass(frozen=True)
class TransitionCandidate:
    id: str
    track_a_id: str
    track_b_id: str
    recipe: Recipe
    output_path: str
    metrics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    rights_status: str = "unknown"
    schema_version: int = 1

    def __post_init__(self):
        if not all((self.id, self.track_a_id, self.track_b_id, self.output_path)):
            raise ValueError("Candidate identity, source IDs and output path are required")
        if self.rights_status not in RIGHTS_STATUSES:
            raise ValueError("Unsupported rights_status")

    def to_dict(self):
        return asdict(self)
