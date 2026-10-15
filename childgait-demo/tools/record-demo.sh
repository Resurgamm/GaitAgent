#!/usr/bin/env bash
#
# Records a walkthrough of the demo to ./demo.mp4.
#
# Elements are resolved from the accessibility tree by label (tools/uidrive.py), not by pixel
# coordinates, so this keeps working when the status bar height, font scale, or scroll offset
# changes. Each step fails loudly instead of tapping into empty space.
#
# Needs a running device with the app installed and both clips in the gallery:
#   ./run-emulator.sh --headless
#   ./tools/make-test-video.sh 4 --push
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/env.sh" >/dev/null

UI="$ROOT/tools/uidrive.py"
OUT="$ROOT/demo.mp4"
DEV_OUT=/sdcard/demo-recording.mp4

# The picker lists durations, not filenames. make-test-video.sh gives the two clips different
# lengths precisely so each can be identified here.
SAGITTAL_DURATION="00:04"
CORONAL_DURATION="00:03"

step() { printf '\n\033[1m·\033[0m %s\n' "$*"; }

adb shell rm -f "$DEV_OUT" >/dev/null 2>&1 || true

step "Starting screen recording"
adb shell screenrecord --bit-rate 6000000 --time-limit 170 "$DEV_OUT" &
RECORD_PID=$!
sleep 3   # let the encoder settle before anything happens on screen

finish() {
  step "Stopping recording"
  # SIGINT lets screenrecord finalise the MP4 container; SIGKILL would truncate it.
  adb shell pkill -SIGINT screenrecord >/dev/null 2>&1 || true
  wait "$RECORD_PID" 2>/dev/null || true
  sleep 3
  adb pull "$DEV_OUT" "$OUT" >/dev/null 2>&1 && echo "wrote $OUT"
  adb shell rm -f "$DEV_OUT" >/dev/null 2>&1 || true
}
trap finish EXIT

step "Import screen"
"$UI" stop >/dev/null; sleep 1
"$UI" launch >/dev/null
"$UI" wait "Add both clips" >/dev/null
sleep 4

step "Adding the sagittal clip"
"$UI" tap-contains "Lateral camera"
"$UI" wait "Recent" >/dev/null
sleep 2
"$UI" tap-contains "duration $SAGITTAL_DURATION"
"$UI" wait "Remove Sagittal clip" --timeout 20 >/dev/null
sleep 3

step "Adding the coronal clip"
"$UI" tap-contains "Walkway-end camera"
"$UI" wait "Recent" >/dev/null
sleep 2
"$UI" tap-contains "duration $CORONAL_DURATION"
"$UI" wait "Analyse session" --timeout 20 >/dev/null
sleep 4

step "Running the analysis"
"$UI" tap-contains "Analyse session"
sleep 5
"$UI" wait "items flagged" --timeout 60 >/dev/null
sleep 5

step "Scrolling the report to the end"
# scroll-to is used rather than a fixed number of swipes: the list length depends on the data,
# and a guessed swipe count is how you end up tapping into empty space.
"$UI" scroll-to "Maximum Trunk Lateral Shift" >/dev/null
sleep 3

step "Opening an item"
"$UI" scroll-to "Hind-foot Varus" --direction down >/dev/null
sleep 1
"$UI" tap-contains "Hind-foot Varus"
"$UI" wait "SCORED FROM" --timeout 20 >/dev/null
sleep 7
"$UI" back >/dev/null; sleep 2

step "Opening a clip"
"$UI" scroll-to "Coronal clip" --direction down >/dev/null
sleep 1
"$UI" tap-contains "Coronal clip"
"$UI" wait "RESOLVED FROM THIS CLIP" --timeout 25 >/dev/null
sleep 8

step "Done"
