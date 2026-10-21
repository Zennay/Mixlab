"""Render a private, static musical cue timeline for a local operator review.

This is an explanatory picture of bounded heuristic proposals, not a mixing
recommendation, confirmed annotation or transition point. No audio/file paths,
source hashes, scripts, links or external resources are embedded.
"""
from __future__ import annotations

from html import escape
from math import isfinite

WIDTH = 960
LEFT = 156
RIGHT = 22
BANDS = (
    ("Beats", "beat_seconds", "#47688c"),
    ("Maatstarts", "downbeat_seconds", "#97614b"),
    ("Frasestarts", "phrase_seconds", "#497e6a"),
)


def _position(second, duration):
    """Display-only pixel position inside the timeline plot."""
    return LEFT + (WIDTH - LEFT - RIGHT) * second / duration


def render_cue_timeline(duration, cue_details, *, clip_id, scale_seconds=None,
                        include_beats=True):
    """Produce offline SVG, optionally omitting a nonexistent manual beatgrid."""
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not isfinite(duration) or duration < 0 or duration > 250):
        raise ValueError("Invalid private excerpt duration")
    if not isinstance(clip_id, str) or not clip_id.startswith("clip-"):
        raise ValueError("Invalid local clip label")
    if scale_seconds is None:
        scale_seconds = duration
    if (isinstance(scale_seconds, bool) or not isinstance(scale_seconds, (int, float))
            or not isfinite(scale_seconds) or scale_seconds < duration
            or scale_seconds > 250):
        raise ValueError("Invalid common cue timeline duration")
    if duration == 0:
        # A valid empty PCM excerpt contains no timeline to scale: do not
        # turn a missing musical proposal into an HTML export failure.
        return ('<p class="cue-timeline">Fragment zonder audiotijd: '
                'geen cue-tijdlijn beschikbaar; handmatige controle vereist.</p>')
    safe_id = escape(clip_id, quote=True)
    title_id = safe_id + "-timeline-title"
    parts = [
        f'<figure class="cue-timeline"><svg viewBox="0 0 {WIDTH} 244" '
        f'role="img" aria-labelledby="{title_id}" xmlns="http://www.w3.org/2000/svg">',
        f'<title id="{title_id}">Tijdlijn van onbevestigde cues voor {safe_id}; '
        'weergegeven tijden zijn uitsluitend voorstellen</title>',
        '<rect x="0" y="0" width="960" height="244" rx="12" fill="#f6f8fa"/>',
        f'<text x="{LEFT}" y="27" font-size="14" fill="#303946">'
        'Tijd in seconden · geen bevestigde mixpunten</text>',
    ]
    # A fixed count of tick labels makes the same UI legible at all durations.
    for fraction in (0, .25, .5, .75, 1):
        x = _position(scale_seconds * fraction, scale_seconds)
        parts.append(
            f'<line x1="{x:.2f}" y1="42" x2="{x:.2f}" y2="205" '
            'stroke="#d4dbe1" stroke-width="1"/>'
            f'<text x="{x:.2f}" y="226" text-anchor="middle" '
            'fill="#36404a" font-size="13">'
            f'{scale_seconds * fraction:.1f}s</text>'
        )
    if type(include_beats) is not bool:
        raise ValueError("Invalid cue lane selection")
    notes = []
    if not include_beats:
        notes.append("Handmatige volledige beatgrid niet opgeslagen; beatrij weggelaten.")
    if scale_seconds > duration:
        endpoint = _position(duration, scale_seconds)
        parts.append(
            f'<rect x="{endpoint:.2f}" y="43" width="{WIDTH - RIGHT - endpoint:.2f}" '
            'height="162" fill="#e9edf1" opacity=".65"/>'
            f'<line x1="{endpoint:.2f}" y1="43" x2="{endpoint:.2f}" y2="205" '
            'stroke="#5f6873" stroke-width="2" stroke-dasharray="4 3"/>'
        )
        notes.append(f"Fragment eindigt op {duration:.1f}s; de as loopt door tot {scale_seconds:.1f}s.")
    for index, (label, key, color) in enumerate(BANDS if include_beats else BANDS[1:]):
        row = 70 + index * 61
        item = cue_details[key]
        count, seconds, truncated = item["count"], item["seconds"], item["truncated"]
        if (type(count) is not int or count < 0 or
                not isinstance(seconds, list) or len(seconds) > 64 or
                type(truncated) is not bool or
                count < len(seconds) or truncated != (count > len(seconds))):
            raise ValueError("Invalid private cue summary")
        parts.append(
            f'<text x="14" y="{row + 6}" font-size="15" fill="#202124">'
            f'{escape(label)} ({count})</text>'
            f'<line x1="{LEFT}" y1="{row}" x2="{WIDTH - RIGHT}" y2="{row}" '
            'stroke="#b0b9c2" stroke-width="2"/>'
        )
        for second in seconds:
            if (isinstance(second, bool) or not isinstance(second, (int, float))
                    or not isfinite(second) or second < 0 or second > duration + .0001):
                raise ValueError("Invalid private cue time")
            x = _position(min(second, duration), scale_seconds)
            parts.append(
                f'<line x1="{x:.2f}" y1="{row - 15}" '
                f'x2="{x:.2f}" y2="{row + 15}" '
                f'stroke="{color}" stroke-width="3"/>'
            )
        if count == 0:
            notes.append(f'{label}: geen betrouwbaar voorstel')
        if truncated:
            notes.append(f'{label}: eerste {len(seconds)} van {count} zichtbaar')
    parts.append('</svg>')
    parts.append(
        '<figcaption>Visuele posities zijn afgerond op schermpixels, de '
        'volledige eerste cue-tijden staan eronder. '
        + escape("; ".join(notes) or "Alle tijden vereisen menselijke controle.")
        + '</figcaption></figure>'
    )
    return "".join(parts)
