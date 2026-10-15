#!/usr/bin/env bash
#
# Boots a project-local emulator, installs the debug APK, and launches the app.
#
# The AVD lives in ./toolchain/avd, so this does not touch the AVDs in your home directory.
#
# Usage:
#   ./run-emulator.sh              boot with a window
#   ./run-emulator.sh --headless   boot without one (useful over SSH / in CI)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$ROOT/env.sh" >/dev/null

export ANDROID_AVD_HOME="$ROOT/toolchain/avd"
mkdir -p "$ANDROID_AVD_HOME"

AVD_NAME="childgait_api35"
IMAGE="system-images;android-35;google_apis;arm64-v8a"
EMULATOR="$ANDROID_HOME/emulator/emulator"

if [ ! -x "$EMULATOR" ]; then
  echo "Emulator is not installed. Run:"
  echo "  source env.sh && sdkmanager --sdk_root=\"\$ANDROID_HOME\" emulator \"$IMAGE\""
  exit 1
fi

if ! "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" list avd -c | grep -qx "$AVD_NAME"; then
  echo "==> Creating AVD $AVD_NAME"
  echo "no" | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" create avd \
    --name "$AVD_NAME" \
    --package "$IMAGE" \
    --device "pixel_6" \
    --force
fi

WINDOW_ARGS=()
if [ "${1:-}" = "--headless" ]; then
  WINDOW_ARGS=(-no-window)
fi

echo "==> Booting $AVD_NAME"
"$EMULATOR" -avd "$AVD_NAME" -no-snapshot -no-audio -gpu swiftshader_indirect "${WINDOW_ARGS[@]}" \
  > "$ROOT/toolchain/emulator-run.log" 2>&1 &

echo "==> Waiting for device"
adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
  sleep 3
done

APK="$ROOT/app/build/outputs/apk/debug/app-arm64-v8a-debug.apk"
if [ ! -f "$APK" ]; then
  echo "==> Building debug APK"
  (cd "$ROOT" && ./gradlew assembleDebug)
fi

echo "==> Installing"
adb install -r "$APK"

echo "==> Launching"
adb shell monkey -p ai.pediamed.childgait -c android.intent.category.LAUNCHER 1 >/dev/null

cat <<EOF

App is running on $AVD_NAME.

  screenshot:  adb exec-out screencap -p > shot.png
  push a video: adb push session.mp4 /sdcard/Movies/
                adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \\
                  -d file:///sdcard/Movies/session.mp4
  stop emulator: adb emu kill

EOF
