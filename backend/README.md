# GaitAgent API Backend

A **FastAPI / Uvicorn** service for two-view pediatric gait assessment. It accepts sagittal and coronal clips, produces 34 binary EVGS scores using a stub or ChildGait-Video checkpoints, and returns JSON or NDJSON events.

[Project overview](../README.md) · [Android frontend](../childgait-demo/README.md) · [Research project](https://pediamedai.com/ChildrenGait/) · [Privacy policy](../PRIVACY.md)

> Research and demonstration use only. Synthetic scores, model predictions, placeholders, and heuristic summaries are not autonomous clinical conclusions.

## Deployment workflow

The backend serves existing, trained checkpoints. There is no training step in the application deployment workflow:

1. Install the inference runtime below.
2. Place the supplied checkpoint files in the sagittal and coronal directories described under **Prepare checkpoints**.
3. Start with `ASSESS_MODE=inference` and verify health before connecting Android.

Model definitions and preprocessing code are included in the repository. No labeled dataset, optimizer setup, or experiment tracker is needed.

## Environment and dependencies

Use **Python 3.11 or 3.12** in a virtual environment. Commands in this README start in `backend/` unless stated otherwise.

`requirements.txt` is the default complete serving environment. It explicitly lists FastAPI, Starlette, Uvicorn, python-multipart, PyTorch, torchvision, timm, numpy, pandas, Pillow, OpenCV, and decord. `requirements-inference.txt` contains the same package list for deployments using that explicit filename. `requirements-stub.txt` is an optional API-only environment for synthetic tests.

GPU deployments require a driver-compatible PyTorch build. Native decoder availability depends on OS and architecture; Linux is the intended EC2 inference environment. These manifests are not a resolved, fully tested lockfile.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

You can use `.\.venv\Scripts\python.exe` directly instead of activating the environment.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

After installing, prepare the checkpoint files and use the inference startup command below.

## Modes and configuration

- **`ASSESS_MODE=stub`**: synthesizes a report from `profiles.json`; no model required.
- **`ASSESS_MODE=inference`**: loads the model runtime and evaluates available checkpoints.
- **Unset or another value**: selects inference if either plane directory contains any `.pth`, otherwise stub. File presence does not establish checkpoint compatibility or coverage.

Set the mode explicitly for reproducible deployments. Environment settings are read during process import; restart after changing them. The service does not automatically load `.env`.

Configuration variables:

- `MODEL_DIR`: checkpoint root; defaults to the repository's `ChildGait-Video/`.
- `CHILDGAIT_ROOT`: model source directory containing `models/`, `dataset/`, and `inference.py`; defaults to the same repository directory.
- `STUB_STREAM_DELAY_S`: delay before each stub score event; default `0.15` seconds, or `0` for fast integration checks.
- `HOST` / `PORT`: read by `run.sh` only; defaults `0.0.0.0` / `8000`. Direct uvicorn commands use their command-line options.

Source and weight directories can differ. Use absolute paths for custom deployments and keep private paths and addresses out of tracked configuration.

Stub output is deterministic for the supplied filenames, byte counts, and profiles. It does not inspect video content and does not guarantee identical values to the Kotlin mock engine.

## Model inference

Defaults are `vit_giant_patch14_224`, 2 classes, 32 frames, sampling interval 2, 224-pixel input, and tubelet size 2. Checkpoints must match the model configuration. Arbitrary VideoMAE weights are not trained EVGS classifiers.

The default model is large. Measure latency, RAM, and GPU memory on your target machine; the repository does not specify a validated minimum GPU configuration.

### Prepare checkpoints

Both directories should exist, even when one is empty:

```text
ChildGait-Video/
+-- sagittal/                  # 11 shared item checkpoints
|   +-- IC.pth                 # Also accepts item_1.pth
|   +-- HL.pth
|   +-- ...
+-- coronal/                   # 6 items x 2 limbs
    +-- HVV_L.pth              # Also accepts item_4_left.pth
    +-- HVV_R.pth              # Also accepts item_4_right.pth
    +-- FRT_L.pth
    +-- ...
```

The fixed item numbering is:

```text
1 IC   2 HL   3 SAD   4 HVV   5 FRT   6 FCL   7 WAD   8 KPA
9 KEX  10 KPS  11 KFX  12 HEX  13 HFX  14 POB  15 PRT  16 TSG  17 TLT
```

- Sagittal items: `IC HL SAD FCL WAD KEX KPS KFX HEX HFX TSG`. The current discovery path selects limb L and accepts names such as `IC.pth`, `IC_L.pth`, and `item_1.pth`.
- Coronal items: `HVV FRT KPA POB PRT TLT`. Include limb labels, e.g. `HVV_L.pth` or `item_14_right.pth`.
- `sagittalL/` and `sagittalR/` are not read by the current backend.
- Sagittal inference runs once, then copies each prediction to both limbs. The active path does not separately infer or horizontally flip right-limb footage.
- A sorting-based fallback exists for unnamed checkpoints. Use explicit names to avoid unintended item assignments.
- Full coverage needs 11 sagittal plus 12 coronal checkpoints, yielding 34 score slots. Partial coverage is allowed and introduces placeholders.

Checkpoint files are not bundled. Provide the already-trained, authorized weights; the service does not need a labeled dataset. Keep private checkpoints out of Git.

### Start inference

```powershell
# Windows, using the default source and checkpoint directories
$env:ASSESS_MODE = "inference"
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

```bash
# macOS / Linux, using the default directories
ASSESS_MODE=inference python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Startup creates the model runtime. CUDA is used when available, otherwise CPU. Checkpoints are swapped sequentially per plane, rather than running 34 models in parallel. Check `mode`, `engine_loaded`, and `checkpoint_counts` in health output; raw file counts do not establish correct item mapping.

The Bash launcher is an alternative after weights have been prepared:

```bash
ASSESS_MODE=inference bash run.sh
```

It installs the default serving dependencies when it creates `.venv`, but does not download weights or configure CUDA. For local access only, bind uvicorn to `127.0.0.1`.

Open [health](http://127.0.0.1:8000/health), [Swagger UI](http://127.0.0.1:8000/docs), or [OpenAPI](http://127.0.0.1:8000/openapi.json). Confirm inference mode and engine availability before submitting video.

### Optional stub for API tests

If you only need synthetic responses, install `requirements-stub.txt` in a separate virtual environment and use `ASSESS_MODE=stub` with the same uvicorn command. No checkpoints or model packages are required. On PowerShell set `$env:ASSESS_MODE = "stub"`; on Bash prefix the command with `ASSESS_MODE=stub`.

## API usage

Examples use a local service on port 8000. Replace video paths with authorized footage. On Windows PowerShell, use `curl.exe`; Bash line continuations below should be adapted for PowerShell or entered on one line.

### GET /health

Reports mode, model directory, checkpoint counts, engine availability, and profile presence. It exposes deployment paths, so restrict access when deploying externally.

### POST /v1/assessments

Accepts two required multipart files:

- `sagittal`: side-view walking clip.
- `coronal`: front/back-view walking clip.

Both video fields are required. Partial checkpoint support does not mean partial uploads are accepted.

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/v1/assessments \
  -F "sagittal=@/path/to/sagittal.mp4" \
  -F "coronal=@/path/to/coronal.mp4"
```

The response contains:

- `patternSummary`: in inference mode, a heuristic based on left/right atypical counts; not a VLM response or diagnosis.
- `clipQuality`: currently fixed at `0.85` in inference mode, not a learned quality estimate.
- `scores`: 34 item/limb entries.
- `_debug`: inference metadata such as mappings and sources; not a stable frontend business contract.

Example score entry:

```json
{
  "item": "IC",
  "itemIndex": 1,
  "limb": "L",
  "label": "TYPICAL",
  "confidence": 0.91,
  "view": "SAGITTAL"
}
```

Labels are `TYPICAL` / `ATYPICAL`, corresponding to model classes 0 / 1. Limbs are `L` / `R`. See [example-response.json](example-response.json) for a full fixture.

### POST /v1/assessments/stream

Accepts the same files and returns `application/x-ndjson`, one JSON object per line. This streams results after complete-file upload; it is neither live camera input nor SSE.

```bash
curl --fail-with-body -N -sS http://127.0.0.1:8000/v1/assessments/stream \
  -F "sagittal=@/path/to/sagittal.mp4" \
  -F "coronal=@/path/to/coronal.mp4"
```

Events:

1. `meta`: `total=34` and `mode=stub|inference`.
2. `score`: one score entry with an additional `type: score`.
3. `done`: summary, quality fields, and all 34 scores.
4. On failure, `{"type":"error","error":"message"}` instead of successful completion.

An HTTP 200 alone does not establish success; wait for `done`. Partial scores must not be treated as a completed report. The stream does not include the JSON endpoint's full `_debug` information or support resumption. Reverse proxies should disable response buffering and allow long-running requests.

### Errors

Ordinary error bodies use `{"error":"message"}`:

- `400`: empty file.
- `422`: missing required multipart fields.
- `503`: inference engine unavailable at request time.
- `500`: JSON assessment inference failed.

Dependency or checkpoint failures at startup can prevent the service from starting. Failures after streaming begins are reported as error events. Complete MIME, format, size, and content validation is not implemented: stub accepts nonempty files without decoding them; inference can fail during decoding.

## Interpretation and current limitations

- Outputs are 17 items x 2 limbs with binary labels, not full EVGS 0/1/2 grades.
- Missing weights yield `TYPICAL`, `confidence=0.0`: unassessed placeholders. The Android UI does not yet show a separate unassessed state.
- Sagittal results are shared between limbs and cannot establish side-specific differences.
- Confidence is the predicted class probability, without calibration in this service.
- The active model entry point does not use bbox, keypoints, or keep_mask. Published research metrics should not be assumed to describe this exact service path.
- Streaming requests create worker threads that share model objects. There is no model lock or inference job queue; submit one model assessment at a time during testing.

## Integration checks

```bash
# Validate the checked-in fixture.
python ../childgait-demo/tools/validate-response.py example-response.json

# Validate your own complete JSON assessment.
curl --fail-with-body -sS http://127.0.0.1:8000/v1/assessments \
  -F "sagittal=@/path/to/sagittal.mp4" \
  -F "coronal=@/path/to/coronal.mp4" \
  | python ../childgait-demo/tools/validate-response.py -
```

Verify inference with your supplied compatible weights. Stub remains available for optional connectivity tests. Contract validation does not validate accuracy, clinical conclusions, input quality, or performance.

Configure Android using ignored `childgait-demo/local.properties` and rebuild the APK. See the [frontend README](../childgait-demo/README.md).

## Deployment and data handling

`deploy-ec2.sh` is an Ubuntu EC2 rsync / SSH / systemd template, not a complete production installer. Despite its stub-oriented header, its generated service currently sets `ASSESS_MODE=inference`. It installs the default API and inference packages, but does not provision model code, checkpoints, or CUDA. Prepare those separately and review its Ubuntu-specific paths.

```bash
# Use only after preparing the controlled host.
PEM=/secure/path/deploy.pem bash deploy-ec2.sh ubuntu@your-host
```

The service lacks built-in authentication, upload limits, rate limiting, and production job scheduling; CORS allows all origins. Configure HTTPS, access control, request limits, proxy timeouts, log handling, and retention rules before external deployment.

Uploads are read into memory and written to OS temporary files. Cleanup is attempted on normal completion and some error paths, but is not guaranteed after interruption or process failure. Logs contain original filenames and errors may expose paths. There is no automatic face blurring or de-identification. Do not commit footage, secrets, reports, logs, or checkpoints.

## File guide

- `requirements.txt`: default API and pretrained-model inference dependencies.
- `requirements-inference.txt`: equivalent explicit inference dependency list.
- `requirements-stub.txt`: optional API-only synthetic-test dependencies.
- `server.py`: routing, startup, uploads, and streaming events.
- `infer_engine.py`: models, checkpoint swapping, and limb mapping.
- `scoring.py`: item definitions, checkpoint names, assembly, and placeholders.
- `stub_synth.py` / `profiles.json`: synthetic report generation.
- `run.sh`: Bash development launcher.
- `deploy-ec2.sh`: Ubuntu deployment template requiring review.
- `example-response.json`: contract fixture. Local NDJSON results are generated artifacts and excluded from Git.
