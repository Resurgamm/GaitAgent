#!/usr/bin/env bash
#
# Watch-rebuild-reinstall-relaunch-screenshot loop.
#
# Edit any Kotlin file or asset and this rebuilds, reinstalls, relaunches the app, and drops a
# fresh screenshot at ./shot.png. Open that file in any previewer that follows changes on disk
# (VS Code's image view, macOS Preview, Quick Look) and you get a live view of the running app
# without Android Studio.
#
# Needs a running device or emulator: ./run-emulator.sh --headless
#
# Usage:
#   ./tools/dev-loop.sh                      screenshot the launch screen each time
#   ./tools/dev-loop.sh --keep-state         relaunch without force-stopping (keeps you in place)
#   ./tools/dev-loop.sh --no-shot            rebuild + install only
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/env.sh" >/dev/null

PKG="ai.pediamed.childgait"
APK="app/build/outputs/apk/debug/app-arm64-v8a-debug.apk"
SHOT="$ROOT/shot.png"

KEEP_STATE=false
TAKE_SHOT=true
for arg in "$@"; do
  case "$arg" in
    --keep-state) KEEP_STATE=true ;;
    --no-shot)    TAKE_SHOT=false ;;
  esac
done

if ! adb get-state >/dev/null 2>&1; then
  echo "No device. Start one first:  ./run-emulator.sh --headless"
  exit 1
fi

# Newest mtime across everything that affects the build.
fingerprint() {
  find app/src app/build.gradle.kts gradle/libs.versions.toml \
    -type f \( -name '*.kt' -o -name '*.json' -o -name '*.xml' -o -name '*.kts' -o -name '*.toml' \) \
    -newermt '1970-01-01' -print0 2>/dev/null \
    | xargs -0 stat -f '%m' 2>/dev/null | sort -rn | head -1
}

cycle() {
  echo "── $(date '+%H:%M:%S') building"
  if ! ./gradlew assembleDebug --console=plain -q 2>&1 | grep -E "^e:|error:|FAILED" ; then
    :
  fi
  if [ ! -f "$APK" ]; then
    echo "   build failed — fix the error above; still watching"
    return
  fi

  adb install -r "$APK" >/dev/null 2>&1 || { echo "   install failed"; return; }

  if [ "$KEEP_STATE" = false ]; then
    adb shell am force-stop "$PKG" >/dev/null 2>&1
  fi
  adb shell am start -n "$PKG/.MainActivity" >/dev/null 2>&1

  if [ "$TAKE_SHOT" = true ]; then
    sleep 3
    adb exec-out screencap -p > "$SHOT" 2>/dev/null && echo "   shot.png updated"
  fi

  # Surface anything the app logged since the relaunch.
  local crash
  crash=$(adb logcat -d -b crash -t 20 2>/dev/null | grep -A6 "$PKG" | head -20)
  [ -n "$crash" ] && { echo "   !! crash:"; echo "$crash" | sed 's/^/      /'; }

  echo "   ready — waiting for changes (ctrl-c to stop)"
}

echo "Watching app/src for changes. Device: $(adb devices | sed -n '2p' | cut -f1)"
cycle
LAST=$(fingerprint)

while true; do
  sleep 1
  NOW=$(fingerprint)
  if [ "$NOW" != "$LAST" ]; then
    LAST="$NOW"
    sleep 0.5          # let the editor finish writing
    cycle
    LAST=$(fingerprint)
  fi
done
