"""ChildGait assessment API.

POST /v1/assessments  multipart: sagittal + coronal
  -> full 34-score JSON (legacy)

POST /v1/assessments/stream  same multipart
  -> NDJSON events: meta, score (per item×limb), done | error

Sagittal is scored once; left and right limb slots share the same prediction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request

from scoring import (
    assemble_assessment,
    expected_score_slots,
    placeholder_score,
)
from stub_synth import synthesize_assessment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("childgait")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = Path(
    os.environ.get("MODEL_DIR", str(REPO_ROOT / "ChildGait-Video"))
).resolve()
PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"
STUB_STREAM_DELAY_S = float(os.environ.get("STUB_STREAM_DELAY_S", "0.15"))

_mode_env = os.environ.get("ASSESS_MODE", "").strip().lower()
_engine = None

_DEFAULT_QUALITY = {
    "SAGITTAL": 0.85,
    "SAGITTAL_L": 0.85,
    "SAGITTAL_R": 0.85,
    "CORONAL": 0.85,
}


def _weights_ready(model_dir: Path) -> bool:
    """True if any plane has at least one .pth (partial uploads OK)."""
    return bool(
        list((model_dir / "sagittal").glob("*.pth"))
        or list((model_dir / "coronal").glob("*.pth"))
    )


def _ckpt_counts(model_dir: Path) -> Dict[str, int]:
    return {
        "sagittal": len(list((model_dir / "sagittal").glob("*.pth"))),
        "coronal": len(list((model_dir / "coronal").glob("*.pth"))),
    }


def _resolve_mode() -> str:
    if _mode_env in ("stub", "inference"):
        return _mode_env
    return "inference" if _weights_ready(DEFAULT_MODEL_DIR) else "stub"


ASSESS_MODE = _resolve_mode()

app = FastAPI(title="ChildGait API", version="0.6.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _save_upload(upload: UploadFile, suffix: str = ".mp4") -> Path:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'clip'} is empty")
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()
        return Path(tmp.name)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _unlink_temps(*paths: Optional[Path]) -> None:
    for p in paths:
        if p is not None:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _score_event(score: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "score",
        "item": score["item"],
        "itemIndex": score.get("itemIndex"),
        "limb": score["limb"],
        "label": score["label"],
        "confidence": float(score["confidence"]),
        "view": score.get("view"),
    }


def _iter_stub_scores(
    *,
    sag_name: str,
    sag_bytes: int,
    cor_name: str,
    cor_bytes: int,
) -> Iterator[Tuple[str, Any]]:
    body = synthesize_assessment(
        sagittal_name=sag_name,
        sagittal_bytes=sag_bytes,
        coronal_name=cor_name,
        coronal_bytes=cor_bytes,
    )
    yield ("meta", {"type": "meta", "total": 34, "mode": "stub"})
    for score in body["scores"]:
        if STUB_STREAM_DELAY_S > 0:
            time.sleep(STUB_STREAM_DELAY_S)
        yield ("score", _score_event(score))
    yield (
        "done",
        {
            "type": "done",
            "patternSummary": body["patternSummary"],
            "clipQuality": body["clipQuality"],
            "scores": body["scores"],
        },
    )


def _iter_inference_scores(sag: Path, cor: Path) -> Iterator[Tuple[str, Any]]:
    if _engine is None:
        raise RuntimeError("Inference engine not loaded")
    yield ("meta", {"type": "meta", "total": 34, "mode": "inference"})
    collected: List[Dict[str, Any]] = []
    seen = set()
    for score in _engine.assess_iter(sag, cor):
        collected.append(score)
        seen.add((score["item"], score["limb"]))
        yield ("score", _score_event(score))

    for code, limb, _plane in expected_score_slots():
        if (code, limb) in seen:
            continue
        ph = placeholder_score(code, limb)
        collected.append(ph)
        seen.add((code, limb))
        yield ("score", _score_event(ph))

    sag_scores = [s for s in collected if s.get("view") == "SAGITTAL"]
    cor_scores = [s for s in collected if s.get("view") == "CORONAL"]
    body = assemble_assessment(
        sag_scores,
        cor_scores,
        clip_quality=dict(_DEFAULT_QUALITY),
        debug={
            "mode": "inference",
            "device": str(_engine.device),
            "streamed": True,
            "sagittal_mirrored_lr": True,
        },
        fill_missing=False,
    )
    yield (
        "done",
        {
            "type": "done",
            "patternSummary": body["patternSummary"],
            "clipQuality": body["clipQuality"],
            "scores": body["scores"],
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    global _engine, ASSESS_MODE
    ASSESS_MODE = _resolve_mode()
    log.info(
        "startup mode=%s MODEL_DIR=%s profiles=%s",
        ASSESS_MODE,
        DEFAULT_MODEL_DIR,
        PROFILES_PATH.is_file(),
    )
    if ASSESS_MODE == "stub" and not PROFILES_PATH.is_file():
        raise RuntimeError(f"stub mode requires {PROFILES_PATH}")
    if ASSESS_MODE == "inference":
        from infer_engine import AssessmentEngine

        try:
            _engine = AssessmentEngine(DEFAULT_MODEL_DIR)
        except Exception:
            log.exception("Failed to load inference engine")
            raise


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode": ASSESS_MODE,
        "model_dir": str(DEFAULT_MODEL_DIR),
        "weights_ready": _weights_ready(DEFAULT_MODEL_DIR),
        "checkpoint_counts": _ckpt_counts(DEFAULT_MODEL_DIR),
        "engine_loaded": _engine is not None,
        "profiles": PROFILES_PATH.is_file(),
    }


@app.post("/v1/assessments")
async def assessments(
    sagittal: UploadFile = File(..., description="Sagittal gait clip (scored once for L and R)"),
    coronal: UploadFile = File(..., description="Frontal gait clip"),
):
    sag: Optional[Path] = None
    cor: Optional[Path] = None
    try:
        sag = await _save_upload(sagittal)
        cor = await _save_upload(coronal)
        log.info(
            "assessment received sagittal=%s (%d B) coronal=%s (%d B) mode=%s",
            sagittal.filename,
            sag.stat().st_size,
            coronal.filename,
            cor.stat().st_size,
            ASSESS_MODE,
        )

        if ASSESS_MODE == "stub":
            body = synthesize_assessment(
                sagittal_name=sagittal.filename or "sagittal.mp4",
                sagittal_bytes=sag.stat().st_size,
                coronal_name=coronal.filename or "coronal.mp4",
                coronal_bytes=cor.stat().st_size,
            )
            return JSONResponse(body)

        if _engine is None:
            raise HTTPException(status_code=503, detail="Inference engine not loaded")

        try:
            sag_scores, cor_scores = _engine.assess(sag, cor)
            body = assemble_assessment(
                sag_scores,
                cor_scores,
                clip_quality=dict(_DEFAULT_QUALITY),
                debug={
                    "mode": "inference",
                    "device": str(_engine.device),
                    "sagittal_ckpts": [s.get("ckpt") for s in sag_scores if s.get("limb") == "L"],
                    "coronal_ckpts": [s.get("ckpt") for s in cor_scores],
                    "sagittal_mirrored_lr": True,
                },
            )
            return JSONResponse(body)
        except Exception as exc:
            log.exception("inference failed")
            raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc
    finally:
        _unlink_temps(sag, cor)


@app.post("/v1/assessments/stream")
async def assessments_stream(
    sagittal: UploadFile = File(..., description="Sagittal gait clip (scored once for L and R)"),
    coronal: UploadFile = File(..., description="Frontal gait clip"),
):
    sag = await _save_upload(sagittal)
    cor = await _save_upload(coronal)
    log.info(
        "stream assessment sagittal=%s (%d B) coronal=%s (%d B) mode=%s",
        sagittal.filename,
        sag.stat().st_size,
        coronal.filename,
        cor.stat().st_size,
        ASSESS_MODE,
    )

    sag_name = sagittal.filename or "sagittal.mp4"
    cor_name = coronal.filename or "coronal.mp4"
    sag_bytes = sag.stat().st_size
    cor_bytes = cor.stat().st_size
    mode = ASSESS_MODE

    if mode == "inference" and _engine is None:
        _unlink_temps(sag, cor)
        raise HTTPException(status_code=503, detail="Inference engine not loaded")

    event_q: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            if mode == "stub":
                it = _iter_stub_scores(
                    sag_name=sag_name,
                    sag_bytes=sag_bytes,
                    cor_name=cor_name,
                    cor_bytes=cor_bytes,
                )
            else:
                it = _iter_inference_scores(sag, cor)
            for kind, payload in it:
                event_q.put((kind, payload))
        except Exception as exc:
            log.exception("stream inference failed")
            event_q.put(("error", {"type": "error", "error": str(exc)}))
        finally:
            event_q.put(None)
            _unlink_temps(sag, cor)

    threading.Thread(target=worker, daemon=True).start()

    async def ndjson() -> Any:
        while True:
            item = await asyncio.to_thread(event_q.get)
            if item is None:
                break
            _kind, payload = item
            yield json.dumps(payload, ensure_ascii=False) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


@app.exception_handler(HTTPException)
async def http_exc_handler(_request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_exc_handler(_request: Request, _exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Request must include multipart parts 'sagittal' and 'coronal'."
        },
    )
