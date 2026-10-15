"""EVGS item table + checkpoint-name parsing + assessment assembly."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger("childgait.scoring")

# Training export index (item_N.pth) → EVGS code. 1-based, fixed contract.
ITEM_INDEX_MAP: Dict[int, str] = {
    1: "IC",
    2: "HL",
    3: "SAD",
    4: "HVV",
    5: "FRT",
    6: "FCL",
    7: "WAD",
    8: "KPA",
    9: "KEX",
    10: "KPS",
    11: "KFX",
    12: "HEX",
    13: "HFX",
    14: "POB",
    15: "PRT",
    16: "TSG",
    17: "TLT",
}

# EVGS code → viewing plane (matches Evgs.kt / validate-response.py)
ITEM_PLANE: Dict[str, str] = {
    "IC": "SAGITTAL",
    "HL": "SAGITTAL",
    "SAD": "SAGITTAL",
    "HVV": "CORONAL",
    "FRT": "CORONAL",
    "FCL": "SAGITTAL",
    "WAD": "SAGITTAL",
    "KPA": "CORONAL",
    "KEX": "SAGITTAL",
    "KPS": "SAGITTAL",
    "KFX": "SAGITTAL",
    "HEX": "SAGITTAL",
    "HFX": "SAGITTAL",
    "POB": "CORONAL",
    "PRT": "CORONAL",
    "TSG": "SAGITTAL",
    "TLT": "CORONAL",
}

# Ordered table derived from the index map (item_1 … item_17)
ITEMS: List[Tuple[str, str]] = [
    (ITEM_INDEX_MAP[i], ITEM_PLANE[ITEM_INDEX_MAP[i]]) for i in range(1, 18)
]
ITEM_CODE_TO_INDEX: Dict[str, int] = {code: idx for idx, code in ITEM_INDEX_MAP.items()}

SAGITTAL_ITEMS = [c for c, p in ITEMS if p == "SAGITTAL"]
CORONAL_ITEMS = [c for c, p in ITEMS if p == "CORONAL"]
LIMBS = ("L", "R")


def items_for_plane(plane: str) -> List[str]:
    plane = plane.upper()
    if plane == "SAGITTAL":
        return list(SAGITTAL_ITEMS)
    if plane == "CORONAL":
        return list(CORONAL_ITEMS)
    raise ValueError(f"Unknown plane: {plane}")


def code_for_item_index(idx: int) -> Optional[str]:
    return ITEM_INDEX_MAP.get(idx)


def item_index_for_code(code: str) -> Optional[int]:
    return ITEM_CODE_TO_INDEX.get(code.upper())


_ITEM_INDEX_RE = re.compile(
    r"^ITEM[_-]?(\d+)(?:[_-]?(LEFT|RIGHT|L|R))?$", re.IGNORECASE
)


def parse_item_file_stem(stem: str) -> Optional[Tuple[str, Optional[str]]]:
    """Parse ``item_N`` / ``item_N_left`` via ``ITEM_INDEX_MAP``.

    Examples: item_1 → IC; item_14_left → (POB, L); item_17_right → (TLT, R).
    """
    m = _ITEM_INDEX_RE.match(stem.strip().replace(" ", ""))
    if not m:
        return None
    idx = int(m.group(1))
    code = code_for_item_index(idx)
    if code is None:
        return None
    limb_raw = m.group(2)
    if limb_raw is None:
        return code, None
    upper = limb_raw.upper()
    return code, ("L" if upper in ("LEFT", "L") else "R")


def parse_ckpt_stem(stem: str) -> Optional[Tuple[str, str]]:
    """Parse checkpoint stem into (item_code, limb).

    Accepted examples: IC_L, IC-L, IC.L, ICL, ic_l, HVV_R,
    item_14_left, item_14_right.
    """
    indexed = parse_item_file_stem(stem)
    if indexed is not None:
        code, limb = indexed
        if limb is not None:
            return code, limb
        return None

    raw = stem.strip()
    upper = raw.upper().replace(" ", "")
    # ITEM_LIMB / ITEM-LIMB / ITEM.LIMB
    for sep in ("_", "-", ".", "__"):
        if sep in upper:
            left, right = upper.rsplit(sep, 1)
            if left in ITEM_PLANE and right in LIMBS:
                return left, right
    # ITEMLIMB glued (e.g. ICL, HVVR) — try longest item codes first
    for code in sorted(ITEM_PLANE.keys(), key=len, reverse=True):
        if upper.startswith(code) and upper[len(code) :] in LIMBS:
            return code, upper[len(code) :]
    return None


def _pth_sort_key(path: Path) -> Tuple[int, int, str]:
    indexed = parse_item_file_stem(path.stem)
    if indexed is not None:
        code = indexed[0]
        return (0, ITEM_CODE_TO_INDEX.get(code, 99), path.name)
    if path.stem.isdigit():
        return (1, int(path.stem), path.name)
    return (2, 0, path.stem.lower())


def discover_sagittal_limb_checkpoints(
    ckpt_dir: Path, limb: str
) -> List[Tuple[Path, str, str]]:
    """Discover sagittal item checkpoints for one fixed limb (L or R).

    Accepts ``IC.pth`` / ``IC_L.pth`` / ``item_1.pth`` (1-based EVGS index).
    Partial sets are allowed — missing items are omitted (filled later).
    """
    limb = limb.upper()
    if limb not in LIMBS:
        raise ValueError(f"limb must be L or R, got {limb}")
    if not ckpt_dir.is_dir():
        raise FileNotFoundError(f"Missing weight directory: {ckpt_dir}")

    paths = sorted(ckpt_dir.glob("*.pth"), key=_pth_sort_key)
    if not paths:
        return []

    named: List[Tuple[Path, str, str]] = []
    for p in paths:
        upper = p.stem.strip().upper().replace(" ", "")
        indexed = parse_item_file_stem(p.stem)
        if indexed is not None:
            item, limb_opt = indexed
            if item not in SAGITTAL_ITEMS:
                continue
            if limb_opt is not None and limb_opt != limb:
                continue
            named.append((p, item, limb))
            continue
        parsed = parse_ckpt_stem(p.stem)
        if parsed is not None:
            item, parsed_limb = parsed
            if item not in SAGITTAL_ITEMS:
                continue
            if parsed_limb != limb:
                continue
            named.append((p, item, limb))
            continue
        # Item-only stem, e.g. IC.pth
        if upper in SAGITTAL_ITEMS:
            named.append((p, upper, limb))

    if named:
        seen = set()
        out: List[Tuple[Path, str, str]] = []
        for row in named:
            if row[1] in seen:
                continue
            seen.add(row[1])
            out.append(row)
        order = {code: i for i, code in enumerate(SAGITTAL_ITEMS)}
        out.sort(key=lambda r: order.get(r[1], 10_000))
        missing = [c for c in SAGITTAL_ITEMS if c not in seen]
        if missing:
            log.warning(
                "%s: partial sagittal weights (%d/%d) missing %s",
                ckpt_dir,
                len(out),
                len(SAGITTAL_ITEMS),
                missing,
            )
        return out

    # Fallback: zip sorted files onto sagittal items in table order (partial OK)
    out = [
        (paths[i], item, limb)
        for i, item in enumerate(SAGITTAL_ITEMS)
        if i < len(paths)
    ]
    log.warning(
        "%s: assigned %d unnamed .pth to sagittal items %s",
        ckpt_dir,
        len(out),
        [r[1] for r in out],
    )
    return out


def discover_plane_checkpoints(plane_dir: Path, plane: str) -> List[Tuple[Path, str, str]]:
    """Return ordered list of (path, item, limb) for a plane weight directory.

    Preference:
      1. Filenames that parse to item+limb (IC_L, item_14_left, …)
      2. Else lexicographic/numeric *.pth assigned to plane items × L,R (partial OK)
    """
    plane = plane.upper()
    allowed = set(items_for_plane(plane))
    if not plane_dir.is_dir():
        return []

    paths = sorted(plane_dir.glob("*.pth"), key=_pth_sort_key)
    if not paths:
        return []

    named: List[Tuple[Path, str, str]] = []
    for p in paths:
        indexed = parse_item_file_stem(p.stem)
        if indexed is not None:
            item, limb_opt = indexed
            if item not in allowed:
                continue
            if limb_opt is None:
                # Sagittal-style item_N in a coronal dir: skip (need left/right)
                continue
            named.append((p, item, limb_opt))
            continue
        parsed = parse_ckpt_stem(p.stem)
        if parsed is None:
            continue
        item, limb = parsed
        if item not in allowed:
            continue
        named.append((p, item, limb))

    if named:
        # Deduplicate by (item, limb), keep first
        seen = set()
        out: List[Tuple[Path, str, str]] = []
        for row in named:
            key = (row[1], row[2])
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        # Stable order: EVGS table order, L then R
        order = {(item, limb): i for i, (item, limb) in enumerate(
            (it, lm) for it in items_for_plane(plane) for lm in LIMBS
        )}
        out.sort(key=lambda r: order.get((r[1], r[2]), 10_000))
        expected = len(items_for_plane(plane)) * len(LIMBS)
        if len(out) < expected:
            log.warning(
                "%s: partial %s weights (%d/%d)",
                plane_dir,
                plane,
                len(out),
                expected,
            )
        return out

    # Fallback: zip files in sorted order onto expected (item, limb) slots (partial OK)
    slots = [(it, lm) for it in items_for_plane(plane) for lm in LIMBS]
    out = [(paths[i], item, limb) for i, (item, limb) in enumerate(slots) if i < len(paths)]
    log.warning(
        "%s: assigned %d unnamed .pth to %s slots",
        plane_dir,
        len(out),
        plane,
    )
    return out


def pred_to_label(pred: int) -> str:
    return "ATYPICAL" if int(pred) == 1 else "TYPICAL"


def placeholder_score(code: str, limb: str) -> Dict[str, Any]:
    """Fill-in for a missing checkpoint: TYPICAL @ confidence 0.0."""
    code = code.upper()
    limb = limb.upper()
    return {
        "item": code,
        "itemIndex": ITEM_CODE_TO_INDEX[code],
        "limb": limb,
        "label": "TYPICAL",
        "confidence": 0.0,
        "view": ITEM_PLANE[code],
        "ckpt": None,
        "inferred": False,
    }


def expected_score_slots() -> List[Tuple[str, str, str]]:
    """All 34 (item, limb, view) slots in EVGS table order."""
    return [(code, limb, plane) for code, plane in ITEMS for limb in LIMBS]


def confidence_from_result(result: Dict[str, Any]) -> float:
    pred = int(result.get("pred", 0))
    probs = result.get("probs") or []
    if isinstance(probs, (list, tuple)) and pred < len(probs):
        return float(max(0.0, min(1.0, float(probs[pred]))))
    return 0.5


def build_pattern_summary(scores: Sequence[Dict[str, Any]]) -> str:
    atypical_r = sum(1 for s in scores if s["limb"] == "R" and s["label"] == "ATYPICAL")
    atypical_l = sum(1 for s in scores if s["limb"] == "L" and s["label"] == "ATYPICAL")
    if atypical_r > atypical_l + 2:
        return (
            "Findings consistent with right-dominant deviation — "
            "more atypical scores on the right limb."
        )
    if atypical_l > atypical_r + 2:
        return (
            "Findings consistent with left-dominant deviation — "
            "more atypical scores on the left limb."
        )
    if atypical_l + atypical_r == 0:
        return "Findings consistent with a typical gait pattern across scored items."
    return (
        "Findings consistent with mixed bilateral deviation — "
        "atypical scores on both limbs."
    )


def assemble_assessment(
    sagittal_scores: List[Dict[str, Any]],
    coronal_scores: List[Dict[str, Any]],
    *,
    clip_quality: Optional[Dict[str, float]] = None,
    debug: Optional[Dict[str, Any]] = None,
    fill_missing: bool = True,
) -> Dict[str, Any]:
    """Merge plane scores into the 34-entry frontend contract.

    Each score's ``item`` / ``itemIndex`` come from ``ITEM_INDEX_MAP``
    (item_1=IC … item_17=TLT). Checkpoint filenames like ``item_14_left.pth``
    resolve through that map before assembly.

    When ``fill_missing`` is True (default), slots without a checkpoint get
    TYPICAL @ confidence 0.0 so partial weight uploads still return a valid body.
    """
    by_key = {(s["item"], s["limb"]): s for s in sagittal_scores + coronal_scores}
    scores: List[Dict[str, Any]] = []
    missing: List[str] = []
    sources: List[Dict[str, Any]] = []
    for code, plane in ITEMS:
        idx = ITEM_CODE_TO_INDEX[code]
        for limb in LIMBS:
            hit = by_key.get((code, limb))
            if hit is None:
                missing.append(f"{code}_{limb}")
                if fill_missing:
                    scores.append(
                        {
                            "item": code,
                            "itemIndex": idx,
                            "limb": limb,
                            "label": "TYPICAL",
                            "confidence": 0.0,
                            "view": plane,
                        }
                    )
                    sources.append(
                        {
                            "item": code,
                            "itemIndex": idx,
                            "limb": limb,
                            "ckpt": None,
                            "inferred": False,
                        }
                    )
                continue
            scores.append(
                {
                    "item": code,
                    "itemIndex": idx,
                    "limb": limb,
                    "label": hit["label"],
                    "confidence": float(hit["confidence"]),
                    "view": plane,
                }
            )
            sources.append(
                {
                    "item": code,
                    "itemIndex": idx,
                    "limb": limb,
                    "ckpt": hit.get("ckpt"),
                    "inferred": True,
                }
            )
    if missing and not fill_missing:
        raise RuntimeError(
            "Incomplete scores; missing: " + ", ".join(missing)
        )
    body: Dict[str, Any] = {
        "patternSummary": build_pattern_summary(scores),
        "clipQuality": clip_quality
        or {"SAGITTAL": 0.85, "SAGITTAL_L": 0.85, "SAGITTAL_R": 0.85, "CORONAL": 0.85},
        "scores": scores,
    }
    dbg = dict(debug or {})
    dbg["item_index_map"] = {str(k): v for k, v in ITEM_INDEX_MAP.items()}
    dbg["score_sources"] = sources
    if missing:
        dbg["missing_scores"] = missing
        dbg["partial_weights"] = True
    body["_debug"] = dbg
    return body
