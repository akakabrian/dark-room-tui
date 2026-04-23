"""CLI entry point."""
from __future__ import annotations

import argparse

from dark_room_tui.app import DarkRoomApp


def main() -> int:
    p = argparse.ArgumentParser(prog="dark-room-tui")
    p.add_argument("--seed", type=int, default=None, help="RNG seed")
    p.add_argument("--mute", action="store_true", help="disable sound")
    args = p.parse_args()
    DarkRoomApp(seed=args.seed, mute=args.mute).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
