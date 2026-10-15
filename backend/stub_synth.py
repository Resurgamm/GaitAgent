"""Stub synthesizer — mirrors Android MockGaitAnalyzer / SessionSynthesizer.

Uses profiles.json (same file as app assets) to draw a coherent 34-score report
when model weights are not available.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from scoring import ITEMS

PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"

# Table 4 published per-item accuracy (matches PathologyProfiles.kt)
_ACC_L = {
    "IC": 0.85, "HL": 0.92, "SAD": 0.81, "WAD": 0.70, "HVV": 0.88,
    "FRT": 0.92, "FCL": 0.89, "KPA": 0.84, "KEX": 0.74, "KPS": 0.82,
    "KFX": 0.78, "HEX": 0.85, "HFX": 0.93, "POB": 0.89, "PRT": 0.89,
    "TSG": 0.85, "TLT": 0.76,
}
_ACC_R = {
    "IC": 0.89, "HL": 0.85, "SAD": 0.74, "WAD": 0.85, "HVV": 0.83,
    "FRT": 0.88, "FCL": 0.93, "KPA": 0.80, "KEX": 0.92, "KPS": 0.86,
    "KFX": 0.81, "HEX": 0.81, "HFX": 0.89, "POB": 0.80, "PRT": 0.74,
    "TSG": 0.92, "TLT": 0.76,
}

_MIN_Q, _MAX_Q = 0.70, 0.97
_JITTER = 0.04


def _seed_from(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _load_profiles() -> List[Dict[str, Any]]:
    with open(PROFILES_PATH) as f:
        doc = json.load(f)
    profiles = doc.get("profiles") or []
    if not profiles:
        raise RuntimeError(f"No profiles in {PROFILES_PATH}")
    return profiles


def _pick_profile(profiles: List[Dict[str, Any]], rng: random.Random) -> Dict[str, Any]:
    total = sum(float(p.get("weight", 1.0)) for p in profiles)
    cursor = rng.random() * total
    for p in profiles:
        cursor -= float(p.get("weight", 1.0))
        if cursor <= 0:
            return p
    return profiles[-1]


def _prob(profile: Dict[str, Any], code: str, limb: str) -> float:
    items = profile.get("items") or {}
    entry = items.get(code) or {}
    key = "left" if limb == "L" else "right"
    return float(entry.get(key, 0.05))


def _confidence(code: str, limb: str, quality: float, rng: random.Random) -> float:
    base = (_ACC_L if limb == "L" else _ACC_R).get(code, 0.80)
    jitter = rng.uniform(-_JITTER, _JITTER)
    return max(0.50, min(0.99, base * (0.88 + 0.12 * quality) + jitter))


def synthesize_assessment(
    *,
    sagittal_name: str,
    sagittal_bytes: int,
    coronal_name: str,
    coronal_bytes: int,
) -> Dict[str, Any]:
    """Deterministic report from clip identities + profiles.json.

    Sagittal L/R share the same label/confidence (single sagittal clip).
    """
    profiles = _load_profiles()
    seed = _seed_from(
        f"{sagittal_name}|{sagittal_bytes}",
        f"{coronal_name}|{coronal_bytes}",
        "score",
    )
    rng = random.Random(seed)
    profile = _pick_profile(profiles, rng)

    sag_q = rng.uniform(_MIN_Q, _MAX_Q)
    quality = {
        "SAGITTAL": sag_q,
        "SAGITTAL_L": sag_q,
        "SAGITTAL_R": sag_q,
        "CORONAL": rng.uniform(_MIN_Q, _MAX_Q),
    }

    scores: List[Dict[str, Any]] = []
    for code, plane in ITEMS:
        if plane == "SAGITTAL":
            q = quality["SAGITTAL"]
            atypical = rng.random() < _prob(profile, code, "L")
            label = "ATYPICAL" if atypical else "TYPICAL"
            conf = round(_confidence(code, "L", q, rng), 3)
            for limb in ("L", "R"):
                scores.append(
                    {
                        "item": code,
                        "limb": limb,
                        "label": label,
                        "confidence": conf,
                        "view": plane,
                    }
                )
        else:
            q = quality["CORONAL"]
            for limb in ("L", "R"):
                atypical = rng.random() < _prob(profile, code, limb)
                scores.append(
                    {
                        "item": code,
                        "limb": limb,
                        "label": "ATYPICAL" if atypical else "TYPICAL",
                        "confidence": round(_confidence(code, limb, q, rng), 3),
                        "view": plane,
                    }
                )

    summary = (
        f"Findings consistent with {profile.get('displayName', 'gait findings')} — "
        f"{profile.get('summary', 'see item scores')}."
    )

    return {
        "patternSummary": summary,
        "clipQuality": {k: round(v, 3) for k, v in quality.items()},
        "scores": scores,
        "_debug": {
            "mode": "stub",
            "profileId": profile.get("id"),
            "profileName": profile.get("displayName"),
            "seed": seed,
            "sagittalName": sagittal_name,
            "sagittalBytes": sagittal_bytes,
            "coronalName": coronal_name,
            "coronalBytes": coronal_bytes,
        },
    }
