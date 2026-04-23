"""Quick diagnostic — does each mapped sound tag resolve to a real file,
and can paplay/afplay actually launch?"""
from __future__ import annotations

import sys
import time

from dark_room_tui.sound import AUDIO_DIR, SOUND_FILES, SoundEngine


def main() -> int:
    se = SoundEngine(enabled=True)
    if not se.enabled:
        print("no audio player found (install pulseaudio-utils or alsa-utils)")
        return 1
    missing = []
    for tag, rel in SOUND_FILES.items():
        p = AUDIO_DIR / rel
        if not p.exists():
            missing.append(rel)
            continue
        print(f"play  {tag:<16} -> {rel}")
        se.play(tag)
        time.sleep(0.25)
    if missing:
        print("\nMissing files:", file=sys.stderr)
        for m in missing:
            print(" ", m, file=sys.stderr)
        return 1
    print("\nall sounds located; playback subprocesses spawned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
