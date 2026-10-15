"""Sequential VideoMAE inference over plane-specific checkpoint dirs.

Sagittal: one shared weight dir ``sagittal/``. Left clip is scored as-is (limb L);
right clip is horizontally flipped before the same weights (limb R).
Coronal: ``coronal/`` as before (item×limb checkpoints).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import torch
from timm.models import create_model

from scoring import (
    ITEM_CODE_TO_INDEX,
    confidence_from_result,
    discover_plane_checkpoints,
    discover_sagittal_limb_checkpoints,
    pred_to_label,
)

log = logging.getLogger("childgait.infer")

REPO_ROOT = Path(__file__).resolve().parent.parent
CGV_ROOT = Path(os.environ.get("CHILDGAIT_ROOT", str(REPO_ROOT / "ChildGait-Video"))).resolve()

if str(CGV_ROOT) not in sys.path:
    sys.path.insert(0, str(CGV_ROOT))

import models  # noqa: E402, F401 — registers vit_* with timm
from inference import (  # noqa: E402  — ChildGait-Video/inference.py
    infer,
    load_and_preprocess_video,
    load_checkpoint,
    resolve_device,
)

CFG = {
    "model": "vit_giant_patch14_224",
    "nb_classes": 2,
    "input_size": 224,
    "short_side_size": 224,
    "num_frames": 32,
    "sampling_rate": 2,
    "tubelet_size": 2,
    "num_segments": 1,
    "drop_path": 0.1,
    "with_checkpoint": False,
    "model_key": "model|module|state_dict",
}


def create_empty_model(cfg: Dict[str, Any]) -> torch.nn.Module:
    return create_model(
        cfg["model"],
        img_size=cfg["input_size"],
        pretrained=False,
        num_classes=cfg["nb_classes"],
        all_frames=cfg["num_frames"] * cfg["num_segments"],
        tubelet_size=cfg["tubelet_size"],
        drop_path_rate=cfg["drop_path"],
        use_mean_pooling=True,
        with_cp=cfg.get("with_checkpoint", False),
    )


class PlaneInferencer:
    """One empty model + sequential weight swap for a checkpoint list."""

    def __init__(
        self,
        plane: str,
        ckpts: List[Tuple[Path, str, str]],
        device: Optional[torch.device] = None,
        cfg: Optional[Dict[str, Any]] = None,
        label: Optional[str] = None,
    ):
        self.plane = plane.upper()
        self.label = label or self.plane
        self.cfg = dict(CFG)
        if cfg:
            self.cfg.update(cfg)
        self.device = device or resolve_device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.ckpts = list(ckpts)
        if not self.ckpts:
            raise RuntimeError(f"No checkpoints for {self.label}")
        self.model = create_empty_model(self.cfg)
        self.model.eval()
        self.model.to(self.device)
        log.info(
            "%s inferencer ready device=%s n_ckpt=%d",
            self.label,
            self.device,
            len(self.ckpts),
        )

    def run_iter(
        self,
        video_path: Path,
        *,
        flip_horizontal: bool = False,
        limb_override: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        video_tensor = load_and_preprocess_video(
            str(video_path),
            clip_len=self.cfg["num_frames"],
            frame_sample_rate=self.cfg["sampling_rate"],
            crop_size=self.cfg["input_size"],
            short_side_size=self.cfg["short_side_size"],
            num_segment=self.cfg["num_segments"],
        )
        # Tensor layout: 1 C T H W — flip width so a right-side view matches left-trained weights.
        if flip_horizontal:
            video_tensor = torch.flip(video_tensor, dims=[-1])
            log.info("%s horizontal flip applied for %s", self.label, video_path.name)

        for ckpt_path, item, limb in self.ckpts:
            out_limb = (limb_override or limb).upper()
            load_checkpoint(
                self.model, str(ckpt_path), model_key=self.cfg["model_key"]
            )
            self.model.eval()
            self.model.to(self.device)
            result = infer(self.model, video_tensor, self.device, return_features=False)
            score = {
                "item": item,
                "itemIndex": ITEM_CODE_TO_INDEX.get(item),
                "limb": out_limb,
                "label": pred_to_label(result["pred"]),
                "confidence": confidence_from_result(result),
                "view": self.plane,
                "ckpt": ckpt_path.name,
                "pred": int(result["pred"]),
                "probs": result.get("probs"),
                "flipped": flip_horizontal,
                "inferred": True,
            }
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
            log.info(
                "%s %s_%s <- %s pred=%s flip=%s",
                self.label,
                item,
                out_limb,
                ckpt_path.name,
                result["pred"],
                flip_horizontal,
            )
            yield score

    def run(
        self,
        video_path: Path,
        *,
        flip_horizontal: bool = False,
        limb_override: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return list(
            self.run_iter(
                video_path,
                flip_horizontal=flip_horizontal,
                limb_override=limb_override,
            )
        )


class AssessmentEngine:
    """Shared sagittal weights; right sagittal clip is mirrored then scored as limb R.

    Partial checkpoint dirs are OK — only present weights are loaded; missing EVGS
    slots are filled by ``assemble_assessment``.
    """

    def __init__(self, model_dir: Path, device: Optional[str] = None):
        model_dir = Path(model_dir)
        dev = resolve_device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        sag_dir = model_dir / "sagittal"
        cor_dir = model_dir / "coronal"
        # item_N.pth (1-based EVGS index); limb tag L is a placeholder, R uses limb_override.
        sag_ckpts = discover_sagittal_limb_checkpoints(sag_dir, "L")
        cor_ckpts = discover_plane_checkpoints(cor_dir, "CORONAL")

        if not sag_ckpts and not cor_ckpts:
            raise RuntimeError(
                f"No .pth checkpoints under {sag_dir} or {cor_dir}"
            )

        self.sagittal: Optional[PlaneInferencer] = (
            PlaneInferencer("SAGITTAL", sag_ckpts, device=dev, label="SAGITTAL")
            if sag_ckpts
            else None
        )
        self.coronal: Optional[PlaneInferencer] = (
            PlaneInferencer("CORONAL", cor_ckpts, device=dev, label="CORONAL")
            if cor_ckpts
            else None
        )
        self.device = dev
        log.info(
            "AssessmentEngine: sagittal=%d ckpts coronal=%d ckpts device=%s "
            "(sagittal run once; L and R share the same scores)",
            len(sag_ckpts),
            len(cor_ckpts),
            dev,
        )

    def assess_iter(
        self,
        sagittal_video: Path,
        coronal_video: Path,
    ) -> Iterator[Dict[str, Any]]:
        """Yield scores: sagittal once (mirrored to L and R), then coronal."""
        if self.sagittal is not None:
            for score in self.sagittal.run_iter(
                Path(sagittal_video), flip_horizontal=False
            ):
                # One forward pass; left and right limbs share the same prediction.
                left = dict(score)
                left["limb"] = "L"
                yield left
                right = dict(score)
                right["limb"] = "R"
                right["flipped"] = False
                yield right
        if self.coronal is not None:
            yield from self.coronal.run_iter(Path(coronal_video))

    def assess(
        self,
        sagittal_video: Path,
        coronal_video: Path,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        scores = list(self.assess_iter(sagittal_video, coronal_video))
        sag = [s for s in scores if s.get("view") == "SAGITTAL"]
        cor = [s for s in scores if s.get("view") == "CORONAL"]
        return sag, cor
