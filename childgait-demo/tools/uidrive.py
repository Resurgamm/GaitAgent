#!/usr/bin/env python3
"""
Drive the app over adb by on-screen text instead of hard-coded pixels.

Hard-coded taps break whenever the status bar height, font scale, or scroll position changes —
which is exactly what happened while I was capturing screenshots. This resolves elements from
the accessibility tree (Compose publishes its semantics there), so a tap goes where the label
actually is.

Usage:
    ./tools/uidrive.py dump                       list every visible text node and its centre
    ./tools/uidrive.py tap "Select session video"
    ./tools/uidrive.py tap-contains "Pass 1"
    ./tools/uidrive.py wait "Session report" [--timeout 40]
    ./tools/uidrive.py swipe up|down [--pixels 1400]
    ./tools/uidrive.py back
    ./tools/uidrive.py shot out.png
    ./tools/uidrive.py launch | stop

Exit status is non-zero when an element is not found, so shell scripts can fail loudly rather
than tapping into empty space.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = "ai.pediamed.childgait"
ACTIVITY = f"{PKG}/.MainActivity"


def adb(*args: str, binary: bool = False):
    result = subprocess.run(
        ["adb", *args], capture_output=True, check=False
    )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", "replace")


def screen_size() -> tuple[int, int]:
    out = adb("shell", "wm", "size")
    m = re.search(r"(\d+)x(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)


def ui_tree() -> ET.Element | None:
    """Dump the accessibility tree. Retries: the dump fails while the UI is animating."""
    for _ in range(4):
        adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
        raw = adb("shell", "cat", "/sdcard/ui.xml")
        if raw.lstrip().startswith("<?xml"):
            try:
                return ET.fromstring(raw)
            except ET.ParseError:
                pass
        time.sleep(0.6)
    return None


def nodes() -> list[tuple[str, int, int]]:
    """Every node carrying text or a content description, with its centre point."""
    root = ui_tree()
    if root is None:
        return []
    found = []
    for node in root.iter("node"):
        label = node.get("text") or node.get("content-desc") or ""
        if not label.strip():
            continue
        bounds = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not bounds:
            continue
        left, top, right, bottom = (int(g) for g in bounds.groups())
        found.append((label, (left + right) // 2, (top + bottom) // 2))
    return found


def find(needle: str, contains: bool) -> tuple[str, int, int] | None:
    for label, x, y in nodes():
        if (needle in label) if contains else (label == needle):
            return (label, x, y)
    return None


def cmd_dump(_: argparse.Namespace) -> int:
    for label, x, y in nodes():
        print(f"{x:5},{y:5}  {label[:70]}")
    return 0


def cmd_tap(args: argparse.Namespace) -> int:
    hit = find(args.text, args.contains)
    if not hit:
        print(f"not found: {args.text!r}", file=sys.stderr)
        return 1
    label, x, y = hit
    adb("shell", "input", "tap", str(x), str(y))
    print(f"tapped {label[:50]!r} at {x},{y}")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        if find(args.text, True):
            print(f"appeared: {args.text!r}")
            return 0
        time.sleep(1.0)
    print(f"timed out waiting for {args.text!r}", file=sys.stderr)
    return 1


def cmd_swipe(args: argparse.Namespace) -> int:
    """Swipe within the middle band of the screen.

    Both ends are kept between 30% and 80% of the height on purpose: starting nearer the top
    puts the gesture on the app bar or the demo banner instead of the list, and the swipe is
    silently swallowed — which looks exactly like a list that has stopped scrolling.
    """
    width, height = screen_size()
    x = width // 2
    near_top = int(height * 0.30)
    near_bottom = int(height * 0.80)
    if args.direction == "up":      # reveal content further down
        adb("shell", "input", "swipe", str(x), str(near_bottom), str(x), str(near_top), "300")
    else:                           # reveal content above
        adb("shell", "input", "swipe", str(x), str(near_top), str(x), str(near_bottom), "300")
    return 0


def cmd_scroll_to(args: argparse.Namespace) -> int:
    """Swipe until the label is on screen. Guessing a swipe count is how you end up tapping
    into empty space on a list whose length depends on the data."""
    for attempt in range(args.max):
        if find(args.text, True):
            print(f"visible after {attempt} swipe(s): {args.text!r}")
            return 0
        cmd_swipe(argparse.Namespace(direction=args.direction, pixels=args.pixels))
        time.sleep(0.8)
    if find(args.text, True):
        print(f"visible after {args.max} swipe(s): {args.text!r}")
        return 0
    print(f"never became visible: {args.text!r}", file=sys.stderr)
    return 1


def cmd_back(_: argparse.Namespace) -> int:
    adb("shell", "input", "keyevent", "KEYCODE_BACK")
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    data = adb("exec-out", "screencap", "-p", binary=True)
    if not data.startswith(b"\x89PNG"):
        print("screencap returned no image", file=sys.stderr)
        return 1
    with open(args.out, "wb") as fh:
        fh.write(data)
    print(f"wrote {args.out} ({len(data)//1024} KB)")
    return 0


def cmd_launch(_: argparse.Namespace) -> int:
    adb("shell", "am", "start", "-n", ACTIVITY)
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    adb("shell", "am", "force-stop", PKG)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("dump").set_defaults(func=cmd_dump)

    for name, contains in (("tap", False), ("tap-contains", True)):
        p = sub.add_parser(name)
        p.add_argument("text")
        p.set_defaults(func=cmd_tap, contains=contains)

    p = sub.add_parser("wait")
    p.add_argument("text")
    p.add_argument("--timeout", type=float, default=40.0)
    p.set_defaults(func=cmd_wait)

    p = sub.add_parser("swipe")
    p.add_argument("direction", choices=["up", "down"])
    p.add_argument("--pixels", type=int, default=1400)
    p.set_defaults(func=cmd_swipe)

    p = sub.add_parser("scroll-to")
    p.add_argument("text")
    p.add_argument("--direction", choices=["up", "down"], default="up")
    p.add_argument("--pixels", type=int, default=1400)
    p.add_argument("--max", type=int, default=12)
    p.set_defaults(func=cmd_scroll_to)

    sub.add_parser("back").set_defaults(func=cmd_back)

    p = sub.add_parser("shot")
    p.add_argument("out")
    p.set_defaults(func=cmd_shot)

    sub.add_parser("launch").set_defaults(func=cmd_launch)
    sub.add_parser("stop").set_defaults(func=cmd_stop)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
