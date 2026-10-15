#!/usr/bin/env bash
#
# Generates the pair of synthetic clips the demo expects — one sagittal, one coronal — and
# optionally pushes them to a running emulator or device.
#
# Uses AVFoundation via Swift, so it needs no ffmpeg, but it is macOS-only.
#
# Usage:
#   ./tools/make-test-video.sh                 -> ./clip-sagittal.mp4 (4s), ./clip-coronal.mp4 (3s)
#   ./tools/make-test-video.sh 5               5s sagittal, 4s coronal
#   ./tools/make-test-video.sh 4 --push        also push both and scan them into the gallery
#
# The two clips are deliberately different lengths. The system photo picker shows durations but
# not filenames, so differing lengths are what lets tools/record-demo.sh pick the right one for
# each slot without resorting to grid coordinates.
#
# NOTE: the figure is a stick figure, so ML Kit will not detect a pose in it. Fine for exercising
# the report and playback; use real footage to test the skeleton overlay.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAG_SECONDS="${1:-4}"
COR_SECONDS=$(( SAG_SECONDS > 3 ? SAG_SECONDS - 1 : 3 ))

SAGITTAL="$ROOT/clip-sagittal.mp4"
CORONAL="$ROOT/clip-coronal.mp4"

echo "==> Generating sagittal ${SAG_SECONDS}s and coronal ${COR_SECONDS}s"
swift "$ROOT/tools/MakeSessionVideo.swift" "$SAGITTAL" sagittal "$SAG_SECONDS"
swift "$ROOT/tools/MakeSessionVideo.swift" "$CORONAL"  coronal  "$COR_SECONDS"

if [ "${2:-}" = "--push" ]; then
  # shellcheck disable=SC1091
  source "$ROOT/env.sh" >/dev/null
  echo "==> Pushing to device"
  for file in "$SAGITTAL" "$CORONAL"; do
    name="$(basename "$file")"
    adb push "$file" "/sdcard/Movies/$name" >/dev/null
    adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
      -d "file:///sdcard/Movies/$name" >/dev/null
    echo "    $name"
  done
  echo "==> Done. Both appear in the app's picker; assign each to its slot."
fi
