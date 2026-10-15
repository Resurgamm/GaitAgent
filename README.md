# GaitAgent

**A research prototype for pediatric gait assessment from ordinary RGB video.** GaitAgent connects two-view walking footage, Edinburgh Visual Gait Score (EVGS) predictions, video review, and report sharing for parents and clinical researchers.

[Project website](https://resurgamm.github.io/GaitAgent/) · [ChildGait-Video research](https://pediamedai.com/ChildrenGait/) · [Android frontend](childgait-demo/README.md) · [API backend](backend/README.md)

> Research and demonstration use only. Stub scores are synthetic. Model predictions require compatible checkpoints and are not a substitute for clinical assessment.

## Overview

The [project website](https://resurgamm.github.io/GaitAgent/) describes GaitAgent as a pediatric gait monitoring and clinical support system. It reports that the core paper, **Decoding Children's Gait Behavior**, was accepted at ECCV 2026. The website describes a CGV dataset of **110 children and 1,185 videos**, with approximately **84% average EVGS accuracy** and **0.83 average F1**. These are reported research results, not measurements reproduced by this working copy.

This repository currently provides:

- An **Android app** for importing sagittal and coronal clips, uploading them, receiving incremental scores, and reviewing reports and videos.
- A **FastAPI service** with health checks, JSON assessments, and NDJSON score streaming.
- **Stub and model inference modes** for integration testing and checkpoint-backed scoring.
- **On-device pose visualization** using ML Kit.
- ChildGait-Video model definitions and video preprocessing for loading supplied pretrained checkpoints. The server performs inference only; no dataset preparation or model optimization is required.

The website also describes clinical VLM Q&A, AR/XR, local de-identification, and live capture. Those capabilities are not fully implemented here. The current app uploads complete selected files before receiving incremental results. The API inference path uses full RGB patch sequences without keypoint prompting or mask-guided pruning; it is not a complete reproduction of the research pipeline.

## Data flow and scoring

```text
Android: select sagittal + coronal clips
                  | multipart upload of complete files
                  v
FastAPI: POST /v1/assessments/stream
  +-- stub: synthesize scores from mock profiles
  +-- inference: run item-specific model checkpoints
                  | NDJSON: meta -> score events -> done
                  v
Android: progress -> report -> video review / JSON sharing
```

EVGS has **17 items per limb**, giving **34 item-and-limb score slots**. This implementation predicts `TYPICAL` or `ATYPICAL`, rather than the full original 0/1/2 ordinal scale.

- **Sagittal:** 11 items / 22 slots: `IC HL SAD FCL WAD KEX KPS KFX HEX HFX TSG`.
- **Coronal:** 6 items / 12 slots: `HVV FRT KPA POB PRT TLT`.
- The backend currently evaluates sagittal footage once and copies each prediction to both limbs. It does not independently assess left/right sagittal differences.
- Missing checkpoints produce `TYPICAL` with `confidence=0.0`. These are unassessed placeholders, not confirmed normal findings.

## Repository layout

```text
.
+-- README.md                       # Project overview
+-- requirements.txt                # Full API + model runtime packages
+-- requirements-inference.txt      # Explicit inference environment packages
+-- requirements-stub.txt           # Lightweight API / synthetic-scoring packages
+-- PRIVACY.md                      # Local privacy and Git submission policy
+-- childgait-demo/                  # Kotlin / Jetpack Compose Android app
|   +-- requirements-frontend.txt   # JDK, Gradle, plugins, Maven dependency inventory
|   +-- requirements-android.txt    # Android SDK package list for sdkmanager
|   +-- app/                        # UI, networking, pose, reports
|   +-- tools/                      # Fixtures, response validation, demo automation
|   +-- docs/                       # Example response and historical handover notes
+-- backend/                        # FastAPI, scoring, stub, inference adapter
+-- ChildGait-Video/                 # Model definitions, preprocessing, inference
+-- inference.py                    # Separate CLI / SageMaker adapter
```

This application branch includes `ChildGait-Video/` as regular source files; cloning it does not require initializing a model submodule. Private datasets, checkpoints, local configuration, and APKs are excluded from source distribution.

## Environment requirements

**Backend:** Python **3.11 or 3.12**. Choose one installation profile from the repository root:

```bash
# Complete API and model runtime (all packages listed directly)
python -m pip install -r requirements.txt

# Lightweight API and synthetic scoring; no PyTorch required
python -m pip install -r requirements-stub.txt

# Equivalent explicit inference profile
python -m pip install -r requirements-inference.txt

```

The runtime profiles explicitly list FastAPI, Starlette, Uvicorn, python-multipart, PyTorch, torchvision, timm, numpy, pandas, Pillow, OpenCV, and decord. These are serving dependencies only; the backend loads existing weights and never starts model optimization. GPU deployments need a driver-compatible PyTorch build. Native decoder support depends on the OS and architecture; Linux is the intended EC2 inference environment. These manifests describe dependencies, not a fully tested lockfile.

**Android:** JDK **17**, Android SDK Platform **35**, Build Tools **35.0.0**, and Platform Tools. Gradle **8.10.2**, AGP **8.7.3**, Kotlin **2.0.21**, and Android libraries are managed by the checked-in Gradle configuration. Install SDK packages with:

```bash
# From childgait-demo/, with sdkmanager on PATH
sdkmanager --package_file=requirements-android.txt
```

The complete frontend toolchain and Maven dependency inventory is in [requirements-frontend.txt](childgait-demo/requirements-frontend.txt). The optional frontend Python tools use only the standard library, so there is no empty frontend pip requirements file. A phone or emulator must run Android **8.0 / API 26** or newer.

## Prepare pretrained checkpoints

Provide compatible, already-trained EVGS checkpoints before starting the backend:

```text
ChildGait-Video/
+-- sagittal/       # 11 shared sagittal item weights, e.g. IC.pth, HL.pth
+-- coronal/        # 12 coronal item/limb weights, e.g. HVV_L.pth, HVV_R.pth
```

Both directories must exist. The model definitions are already included; you only need to supply the checkpoint files for inference. No labeled dataset, optimizer, or experiment tracker is needed. Use `MODEL_DIR` to point to a different weight root and keep `CHILDGAIT_ROOT` pointed at the bundled model source. Full naming rules are in the [backend README](backend/README.md).

## Quick start: pretrained-weight inference

### 1. Start the backend

From the repository root, use a virtual environment.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd backend
$env:ASSESS_MODE = "inference"
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd backend
ASSESS_MODE=inference python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Open [health](http://127.0.0.1:8000/health) and [API docs](http://127.0.0.1:8000/docs). Confirm `mode: inference`, `engine_loaded: true`, and the expected checkpoint counts. Model setup or checkpoint errors must be resolved before app assessments can run.

### 2. Configure and build Android

Open `childgait-demo/` in Android Studio. Configure JDK 17 and the required SDK packages. Create or update its ignored `local.properties`:

```properties
# Replace with your own SDK path; use forward slashes on Windows.
sdk.dir=C:/Android/Sdk
# Android Studio emulator -> host computer
api.baseUrl=http://10.0.2.2:8000
```

For a USB-connected phone, run `adb reverse tcp:8000 tcp:8000` and use `http://127.0.0.1:8000`. A phone on the same LAN can use the development computer's LAN address. Keep real deployment addresses out of tracked configuration.

In another terminal:

```powershell
cd childgait-demo
.\gradlew.bat assembleDebug
adb install -r app/build/outputs/apk/debug/app-arm64-v8a-debug.apk
```

On macOS / Linux, use `./gradlew assembleDebug`. Select the x86_64 APK for an x86_64 emulator, or use the universal APK. The address is compiled into the app: rebuild and reinstall after changing it. See the [frontend README](childgait-demo/README.md) for the optional Apple Silicon toolchain.

### 3. Run an assessment

1. Select a side-view clip in **Sagittal** and a front/back-view clip in **Coronal**.
2. With both slots filled, tap **Analyse session**.
3. Wait for upload, then review incremental scores and the 34-slot report.
4. Open an item or clip to inspect its source view and video.
5. Share JSON if needed, after checking filenames and report contents.

The remote client currently defaults to `isMock=false` and does not synchronize that flag from the backend's `meta.mode`. Check `/health` rather than relying on the banner. Exported JSON also retains a fixed synthetic/mock disclaimer, even for remote inference.

## Optional API-only stub

For UI or connectivity testing without weights, install `requirements-stub.txt` instead of the full runtime and start with `ASSESS_MODE=stub`. The backend generates synthetic scores and does not analyze video content. On PowerShell set `$env:ASSESS_MODE = "stub"` before the uvicorn command; on Bash prefix it with `ASSESS_MODE=stub`.

The default deployment instructions above use real inference from supplied checkpoints. Weights and datasets are not bundled; keep private checkpoint files outside source control.

## Development checks

```powershell
# From childgait-demo/
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug

# From the repository root
python childgait-demo/tools/validate-response.py childgait-demo/docs/example-response.json
```

Use `./gradlew` on macOS / Linux. Unit tests cover synthesis, reproducibility, profile consistency, and view assignment. They do not establish model accuracy. Measure inference latency, memory use, and pose quality on the target hardware and authorized footage.

## Privacy and deployment

- Remote mode uploads original video. The backend writes temporary files, attempts cleanup after processing, and logs filenames. Automatic upload de-identification is not implemented.
- The API has no built-in authentication, upload limits, or rate limiting; CORS allows all origins. External deployment needs HTTPS, access control, upload limits, and retention policies.
- Android cloud backup is disabled, but the APK still contains its configured service address.
- Do not commit credentials, local properties, patient footage, screenshots, reports, or weights. Follow [PRIVACY.md](PRIVACY.md) and inspect staged changes.

## Research and licensing

Research context and reported metrics come from the [GaitAgent website](https://resurgamm.github.io/GaitAgent/) and [ChildGait-Video project](https://pediamedai.com/ChildrenGait/). Use the formal paper's bibliographic information for citations.

This working copy has no repository-wide `LICENSE` file. Confirm permission separately for source code, third-party dependencies, model weights, and pediatric data.
