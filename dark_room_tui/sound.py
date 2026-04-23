"""Vendor-FLAC sound playback. Fire-and-forget subprocesses.

Uses paplay on Linux / afplay on macOS. If nothing's available the module
silently disables itself — we never crash the game over audio.

Debounces each sound to 150 ms so rapid-fire emits don't stack up.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


AUDIO_DIR = (
    Path(__file__).resolve().parent.parent / "vendor" / "adarkroom" / "audio"
)

# Engine emits short sound tags; map to vendor .flac files.
SOUND_FILES: dict[str, str] = {
    "lightFire":      "light-fire.flac",
    "stokeFire":      "stoke-fire.flac",
    "fireDead":       "fire-dead.flac",
    "fireSmoldering": "fire-smoldering.flac",
    "fireFlickering": "fire-flickering.flac",
    "fireBurning":    "fire-burning.flac",
    "fireRoaring":    "fire-roaring.flac",
    "build":          "build.flac",
    "craft":          "craft.flac",
    "buy":            "craft.flac",
    "gatherWood":     "gather-wood.flac",
    "checkTraps":     "check-traps.flac",
    "embark":         "embark.flac",
    "eatMeat":        "eat-meat.flac",
    "death":          "death.flac",
    "encounter1":     "encounter-tier-1.flac",
    "encounter2":     "encounter-tier-2.flac",
    "encounter3":     "encounter-tier-3.flac",
    "reinforceHull":  "reinforce-hull.flac",
    "upgradeEngine":  "upgrade-engine.flac",
    "liftOff":        "lift-off.flac",
    "footstep1":      "footsteps-1.flac",
    "footstep2":      "footsteps-2.flac",
    "footstep3":      "footsteps-3.flac",
    "footstep4":      "footsteps-4.flac",
    "footstep5":      "footsteps-5.flac",
}

DEBOUNCE_S = 0.15


def _detect_player() -> list[str] | None:
    # Return argv template; path appended by caller.
    if shutil.which("paplay"):
        return ["paplay"]
    if shutil.which("aplay"):
        return ["aplay", "-q"]
    if shutil.which("afplay"):  # macOS
        return ["afplay"]
    return None


class SoundEngine:
    def __init__(self, enabled: bool = True) -> None:
        self._player = _detect_player() if enabled else None
        self._last_play: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self._player is not None

    def play(self, tag: str) -> None:
        if not self.enabled:
            return
        rel = SOUND_FILES.get(tag)
        if not rel:
            return
        path = AUDIO_DIR / rel
        if not path.exists():
            return
        now = time.monotonic()
        if now - self._last_play.get(tag, 0.0) < DEBOUNCE_S:
            return
        self._last_play[tag] = now
        try:
            subprocess.Popen(
                [*self._player, str(path)],  # type: ignore[misc]
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            # disable further attempts if player vanished
            self._player = None
