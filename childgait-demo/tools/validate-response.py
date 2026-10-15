#!/usr/bin/env python3
"""
Validate a backend `/v1/assessments` response against what the app requires.

Run this against your own output before wiring the app to it. Every rule checked here is one the
app depends on; violating any of them produces a report that is silently wrong rather than a
visible error, which is the failure mode worth spending a script to avoid.

Usage:
    ./tools/validate-response.py response.json
    curl -s ... | ./tools/validate-response.py -
    ./tools/validate-response.py docs/example-response.json     # the known-good fixture

Exit status is 0 when the response is valid, 1 otherwise.
"""
from __future__ import annotations

import json
import sys

# The authoritative item table, mirroring data/model/Evgs.kt.
# code -> (item number, plane)
ITEMS: dict[str, tuple[int, str]] = {
    "IC":  (1,  "SAGITTAL"),
    "HL":  (2,  "SAGITTAL"),
    "SAD": (3,  "SAGITTAL"),
    "HVV": (4,  "CORONAL"),
    "FRT": (5,  "CORONAL"),
    "FCL": (6,  "SAGITTAL"),
    "WAD": (7,  "SAGITTAL"),
    "KPA": (8,  "CORONAL"),
    "KEX": (9,  "SAGITTAL"),
    "KPS": (10, "SAGITTAL"),
    "KFX": (11, "SAGITTAL"),
    "HEX": (12, "SAGITTAL"),
    "HFX": (13, "SAGITTAL"),
    "POB": (14, "CORONAL"),
    "PRT": (15, "CORONAL"),
    "TSG": (16, "SAGITTAL"),
    "TLT": (17, "CORONAL"),
}

LIMBS = {"L", "R"}
LABELS = {"TYPICAL", "ATYPICAL"}
PLANES = {"SAGITTAL", "CORONAL"}
# Prefer three camera slots; still accept legacy two-plane keys.
QUALITY_KEYS_PREFERRED = {"SAGITTAL_L", "SAGITTAL_R", "CORONAL"}
QUALITY_KEYS_LEGACY = {"SAGITTAL", "CORONAL"}

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def validate(doc: object) -> None:
    if not isinstance(doc, dict):
        fail("top level must be a JSON object")
        return

    # --- patternSummary -----------------------------------------------------
    summary = doc.get("patternSummary")
    if not isinstance(summary, str) or not summary.strip():
        fail("patternSummary: required, must be a non-empty string")
    elif len(summary) > 400:
        warn(f"patternSummary is {len(summary)} chars; the summary card expects roughly < 200")

    # --- clipQuality --------------------------------------------------------
    quality = doc.get("clipQuality")
    if not isinstance(quality, dict):
        fail("clipQuality: required, must be an object keyed by camera slot / plane")
    else:
        keys = set(quality.keys())
        if QUALITY_KEYS_PREFERRED <= keys:
            required = QUALITY_KEYS_PREFERRED
        elif QUALITY_KEYS_LEGACY <= keys:
            required = QUALITY_KEYS_LEGACY
            warn("clipQuality uses legacy SAGITTAL/CORONAL keys; prefer SAGITTAL_L/SAGITTAL_R/CORONAL")
        else:
            fail(
                "clipQuality: expected keys SAGITTAL_L, SAGITTAL_R, CORONAL "
                "(or legacy SAGITTAL, CORONAL)"
            )
            required = set()
        for key in required:
            value = quality[key]
            if not isinstance(value, (int, float)):
                fail(f"clipQuality.{key}: must be a number, got {type(value).__name__}")
            elif not 0.0 <= value <= 1.0:
                fail(f"clipQuality.{key}: {value} is outside 0..1")
        for key in quality:
            if key not in QUALITY_KEYS_PREFERRED and key not in QUALITY_KEYS_LEGACY:
                fail(f"clipQuality.{key}: unknown key")

    # --- scores -------------------------------------------------------------
    scores = doc.get("scores")
    if not isinstance(scores, list):
        fail("scores: required, must be an array of 34 objects")
        return

    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(scores):
        where = f"scores[{index}]"
        if not isinstance(entry, dict):
            fail(f"{where}: must be an object")
            continue

        code = entry.get("item")
        limb = entry.get("limb")
        label = entry.get("label")
        confidence = entry.get("confidence")

        if code not in ITEMS:
            fail(f"{where}.item: {code!r} is not a known EVGS code")
        if limb not in LIMBS:
            fail(f"{where}.limb: {limb!r} must be 'L' or 'R'")
        if label not in LABELS:
            fail(f"{where}.label: {label!r} must be 'TYPICAL' or 'ATYPICAL'")
        if not isinstance(confidence, (int, float)):
            fail(f"{where}.confidence: must be a number, got {type(confidence).__name__}")
        elif not 0.0 <= confidence <= 1.0:
            fail(f"{where}.confidence: {confidence} is outside 0..1")

        # The `view` field is optional; if present it must agree with the item's plane, because
        # the app derives the plane from the item and would ignore a contradictory value.
        view = entry.get("view")
        if view is not None and code in ITEMS and view != ITEMS[code][1]:
            fail(
                f"{where}.view: says {view} but {code} is only resolvable from "
                f"{ITEMS[code][1]}"
            )

        if code in ITEMS and limb in LIMBS:
            key = (code, limb)
            if key in seen:
                fail(f"{where}: duplicate score for {limb}-{code}")
            seen.add(key)

    # --- completeness -------------------------------------------------------
    expected = {(code, limb) for code in ITEMS for limb in LIMBS}
    missing = sorted(f"{limb}-{code}" for code, limb in expected - seen)
    if missing:
        fail(
            f"scores: {len(missing)} of 34 entries missing — the report table has a row for "
            f"every one, so a gap renders as an empty cell: {', '.join(missing)}"
        )

    if len(scores) != 34 and not missing:
        fail(f"scores: expected exactly 34 entries, got {len(scores)}")

    # --- plane split --------------------------------------------------------
    if not missing:
        sagittal = sum(1 for code, _ in seen if ITEMS[code][1] == "SAGITTAL")
        coronal = sum(1 for code, _ in seen if ITEMS[code][1] == "CORONAL")
        if sagittal != 22:
            fail(f"expected 22 sagittal scores (11 items x 2 limbs), got {sagittal}")
        if coronal != 12:
            fail(f"expected 12 coronal scores (6 items x 2 limbs), got {coronal}")

    # --- soft sanity checks -------------------------------------------------
    numeric = [s["confidence"] for s in scores
               if isinstance(s, dict) and isinstance(s.get("confidence"), (int, float))]
    if numeric:
        if all(c == numeric[0] for c in numeric):
            warn(
                f"every confidence is identical ({numeric[0]}) — the UI shows these per item, so "
                "a constant reads as a placeholder"
            )
        if max(numeric) <= 1.0 and min(numeric) < 0.05:
            warn("some confidences are near zero; check you are not sending 0..100 as 0..1")

    flagged = sum(1 for s in scores
                  if isinstance(s, dict) and s.get("label") == "ATYPICAL")
    if flagged == 34:
        warn("all 34 items flagged atypical — plausible but rare; worth double-checking")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    source = sys.argv[1]
    try:
        raw = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
    except OSError as exc:
        print(f"cannot read {source}: {exc}", file=sys.stderr)
        return 1

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        return 1

    validate(doc)

    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"error:   {message}")

    if errors:
        print(f"\nINVALID — {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1

    print(f"VALID — 34 scores, plane split correct, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
