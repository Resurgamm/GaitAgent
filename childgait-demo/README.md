# GaitAgent Android Frontend

An Android research app built with **Kotlin and Jetpack Compose**. The package name and some UI labels retain the ChildGait name: `ai.pediamed.childgait`. The app handles two-view video import, remote scoring, reports, playback, and on-device pose visualization.

[Project overview](../README.md) · [Backend setup](../backend/README.md) · [Project website](https://resurgamm.github.io/GaitAgent/) · [Privacy policy](../PRIVACY.md)

## Features and scope

- Separate **Sagittal** (side-view) and **Coronal** (front/back-view) import slots.
- Complete-file multipart uploads and incremental NDJSON score updates.
- A 34-slot report grouped by body region, with limb labels, confidence, and source views.
- Media3 / ExoPlayer playback with ML Kit skeleton overlays.
- JSON report sharing through Android's share sheet.
- An optional local mock engine and JVM tests.

Live camera capture, clinical VLM Q&A, AR interfaces, and automatic pre-upload de-identification are not implemented. The default app uses the network backend and does not fall back to a local mock when the connection fails. This is a research prototype, not an autonomous diagnostic tool.

## Requirements

Install these tools separately from Python:

- **JDK 17**.
- **Android SDK Platform 35**, **Build Tools 35.0.0**, and **Platform Tools / adb**.
- Android Studio, or an equivalent command-line Android environment.
- A device running **Android 8.0 / API 26** or later.

Gradle **8.10.2**, AGP **8.7.3**, Kotlin **2.0.21**, Compose, ML Kit, OkHttp, and other Android dependencies are already declared in the wrapper, `gradle/libs.versions.toml`, and `app/build.gradle.kts`. Gradle downloads them during the build.

The SDK package list is [requirements-android.txt](requirements-android.txt). With `sdkmanager` available, run from this directory:

```bash
sdkmanager --package_file=requirements-android.txt
sdkmanager --licenses
```

[requirements-frontend.txt](requirements-frontend.txt) lists the actual toolchain versions, all four Gradle plugins, and all 19 Maven library declarations from the build configuration, including the Compose BOM. It is an environment inventory, not a pip input file. Install Android libraries through Gradle and SDK packages through `sdkmanager`. The optional scripts in `tools/` need Python **3.11 or 3.12**, but no third-party Python packages; no empty frontend pip requirements file is provided.

## Build and install

All commands below run from `childgait-demo/`.

### Android Studio / Windows / Linux

Open this directory in Android Studio, choose JDK 17, and install the SDK requirements. Create or update ignored `local.properties`:

```properties
# Use your own SDK location.
sdk.dir=C:/Android/Sdk
api.baseUrl=http://10.0.2.2:8000
```

Use forward slashes for Windows paths. On macOS / Linux, enter the SDK's absolute path. Do not append `/v1` to the service base URL.

```powershell
# Windows PowerShell
.\gradlew.bat assembleDebug
adb devices
adb install -r app/build/outputs/apk/debug/app-arm64-v8a-debug.apk
```

```bash
# macOS / Linux
./gradlew assembleDebug
adb devices
adb install -r app/build/outputs/apk/debug/app-arm64-v8a-debug.apk
```

Outputs are in `app/build/outputs/apk/debug/`:

- `app-arm64-v8a-debug.apk`: ARM64 phones and emulators.
- `app-x86_64-debug.apk`: x86_64 emulators.
- `app-universal-debug.apk`: both supported ABIs.

Build your own APK rather than relying on an older prebuilt file, which may contain an obsolete service address. APKs are excluded from source control.

### Optional Apple Silicon toolchain

`setup-toolchain.sh` downloads a **macOS ARM64 JDK and macOS Android tools**. It is not a Windows, Linux, or Intel Mac installer.

```bash
bash setup-toolchain.sh
source env.sh
# Now add api.baseUrl to local.properties.
./gradlew assembleDebug
```

Tools and caches live in `toolchain/` and require several GB of disk space and network downloads. **Rerunning setup overwrites local.properties**; re-add your API setting afterward. Android Studio does not read `env.sh`: set its Gradle JDK to `toolchain/jdk` and Gradle user home to `toolchain/gradle-home` when using this setup.

## Connect to the backend

`app/build.gradle.kts` reads `api.baseUrl` into `BuildConfig.API_BASE_URL`; `di/AppModule.kt` creates the remote analyzer. The fallback is `http://10.0.2.2:8000`.

- **Android Studio emulator:** use `http://10.0.2.2:8000` to reach the host computer.
- **USB phone:** run `adb reverse tcp:8000 tcp:8000`, then use `http://127.0.0.1:8000`.
- **LAN phone:** use the development computer's LAN address. Bind the backend to `0.0.0.0` and ensure the device can reach the port.
- **Remote service:** keep its HTTPS address in local configuration. Authentication requires additional integration; there is no built-in login or token configuration.

**Rebuild and reinstall after each address change.** There is no runtime server settings screen. Do not put private deployment addresses in tracked source; the compiled APK will still contain the selected address.

For normal use, supply the backend with pretrained checkpoints and start it in `inference` mode. Check `/health` for `mode: inference`, `engine_loaded: true`, and checkpoint coverage. The optional `stub` mode is only for synthetic connectivity tests and still receives uploaded video files.

## Use the app

1. Start the backend and confirm device connectivity.
2. Choose side-view footage for **Sagittal** and front/back-view footage for **Coronal**.
3. Tap **Analyse session** once both slots are filled.
4. Wait for full upload, followed by incremental score events.
5. Review the report, open items to inspect view attribution, and replay clips.
6. Share JSON only after reviewing report contents and video filenames.

View assignments are declared by the user, not automatically detected. Use short, clear footage you are authorized to upload. The client reads both files into memory to construct the request, so large files can cause memory pressure.

## Interpret results

The app displays **17 items per limb / 34 slots** as `TYPICAL` or `ATYPICAL`, not full EVGS 0/1/2 grades. Eleven items use sagittal footage and six use coronal footage.

Current backend limitations:

- Sagittal predictions are copied to both limbs rather than evaluated independently.
- Missing checkpoints produce `TYPICAL` with zero confidence; the UI does not yet distinguish these unassessed placeholders.
- Inference `clipQuality` is currently fixed, not predicted.

The remote client defaults to `isMock=false` and does not synchronize the flag from `meta.mode`. A stub backend does not automatically enable the mock banner. Conversely, `ReportExport.kt` always emits a synthetic/mock disclaimer. Use backend configuration and health information to identify the actual mode.

### Local mock development

The local mock has no UI toggle and is disabled by default. For offline demonstrations, import `MockGaitAnalyzer` and `ProfileLibrary` in `AppModule.kt`, then replace its analyzer factory:

```kotlin
import ai.pediamed.childgait.data.engine.MockGaitAnalyzer
import ai.pediamed.childgait.data.engine.ProfileLibrary

// Replace the existing function inside AppModule.
fun gaitAnalyzer(context: Context): GaitAnalyzer =
    MockGaitAnalyzer {
        ProfileLibrary.load(
            context.applicationContext.assets.open("mock/profiles.json")
        )
    }
```

Rebuild and reinstall. This mode synthesizes deterministic results from clip metadata and profiles; it does not analyze gait. Python stub and Kotlin mock do not guarantee identical values.

## Pose visualization

`pose/PoseTracker.kt` runs ML Kit on sampled video frames: target 12 fps, maximum 60 frames, longest image edge 640 pixels. Playback displays the nearest sampled skeleton.

These keypoints are not sent into the backend scoring model and do not blur faces before upload. Synthetic stick figures may yield no pose detections; they can exercise the UI without validating real-person overlays.

## Tests and tools

```powershell
# Windows
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug
python tools/validate-response.py docs/example-response.json
```

```bash
# macOS / Linux
./gradlew testDebugUnitTest lintDebug assembleDebug
python3 tools/validate-response.py docs/example-response.json
```

Tests cover synthetic scoring, profile consistency, and view partitioning. The response validator checks the 34-slot contract; neither verifies medical accuracy.

- `tools/make-test-video.sh 4 --push`: creates synthetic clips with Swift / AVFoundation; **macOS only**.
- `run-emulator.sh [--headless]`: starts a project-local API 35 ARM64 AVD and installs the app.
- `tools/uidrive.py`: drives the app by adb accessibility labels, e.g. `python3 tools/uidrive.py dump`.
- `tools/dev-loop.sh`: Bash-based watch, build, install, and screenshot loop using the local toolchain.
- `tools/record-demo.sh`: records a walkthrough; depends on particular UI labels and clip durations.

For the Apple Silicon emulator workflow:

```bash
source env.sh
sdkmanager --sdk_root="$ANDROID_HOME" emulator "system-images;android-35;google_apis;arm64-v8a"
bash run-emulator.sh
bash tools/make-test-video.sh 4 --push
```

The emulator script reuses an existing APK. Build explicitly after changing source or configuration.

## Source map

```text
app/src/main/java/ai/pediamed/childgait/
+-- di/AppModule.kt                    # Analyzer and service address
+-- data/model/                        # EVGS, clips, sessions, reports
+-- data/engine/RemoteGaitAnalyzer.kt   # Multipart / NDJSON client
+-- data/engine/MockGaitAnalyzer.kt     # Local mock
+-- data/engine/SessionSynthesizer.kt  # Pure Kotlin synthesis
+-- pose/                              # ML Kit extraction
+-- ui/screens/                        # Import, progress, reports, playback
+-- ui/components/                     # Skeleton and banners
+-- util/ReportExport.kt               # JSON sharing
```

`docs/example-response.json` is an integration fixture. The handover Markdown and HTML are historical design notes; use current code and this README when their descriptions conflict.

## Troubleshooting

- **Connection failure:** check health, device routing, firewall access, and whether the APK was rebuilt after changing the URL.
- **No scores yet:** full upload precedes scoring. Client connect / read / write timeouts are 30 / 600 / 300 seconds.
- **No skeleton:** check video decoding and visible human subjects; synthetic or heavily occluded footage may not be detected.
- **Zero confidence:** inspect backend checkpoint coverage and names; do not interpret placeholders as normal findings.
- **SDK errors:** update the local SDK path; re-add API configuration after rerunning setup.

## Privacy

Remote mode uploads original clips without automatic de-identification. Cloud backup is disabled, but shared reports include display filenames. Cleartext HTTP is allowed for development; use HTTPS for external deployment. Keep patient footage, screenshots, reports, signing keys, local configuration, and APKs out of Git. See [PRIVACY.md](../PRIVACY.md).
