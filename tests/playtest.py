"""Scripted playtest — boot the TUI, drive a short session, save SVGs.

We use Textual's `Pilot` rather than pexpect because the pty transport
interleaves ANSI escape sequences that don't survive round-tripping back
through Textual's renderer.  `Pilot` is the in-process equivalent that
Textual itself uses for testing, and we get `app.save_screenshot()` for
free.  The pexpect/ptyprocess dependency is still installed so an end-to-
end smoke can be added later if needed.

Run:

    python -m tests.playtest

Artifacts land in `tests/out/playtest_<step>.svg`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dark_room_tui.app import DarkRoomApp


OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)


async def _playtest() -> None:
    app = DarkRoomApp(seed=42, mute=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.save_screenshot(str(OUT_DIR / "playtest_01_boot.svg"))

        # seed wood so light + stoke land immediately
        app.engine.stores_set("wood", 20)
        await pilot.press("l")
        await pilot.pause()
        app.engine.advance(11)  # clear stoke cooldown
        await pilot.press("s")
        await pilot.pause()
        app.save_screenshot(str(OUT_DIR / "playtest_02_fire_lit.svg"))

        # fast-forward the builder/forest chain
        app.engine.advance(60)
        app.engine.collect_income(60)
        await pilot.pause()

        # swap to outside, gather once
        await pilot.press("2")
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        app.save_screenshot(str(OUT_DIR / "playtest_03_gathered.svg"))

        # build a trap: push to warm+helper then invoke
        app.engine.set("game", "builder", "level", value=4)
        app.engine.set("game", "temperature", value={"value": 4})
        app.engine.stores_set("wood", 100)
        await pilot.press("1")  # return to room
        await pilot.pause()
        await pilot.press("t")  # trap
        await pilot.pause()
        app.save_screenshot(str(OUT_DIR / "playtest_04_trap_built.svg"))

        # scroll the log — PageUp on the RichLog (ensure focus first)
        if app._event_log is not None:
            app._event_log.scroll_up(animate=False)
            await pilot.pause()
        app.save_screenshot(str(OUT_DIR / "playtest_05_log_scrolled.svg"))

        # quit
        await pilot.press("q")
        await pilot.pause()

    print("playtest ok —", OUT_DIR)


def main() -> None:
    asyncio.run(_playtest())


if __name__ == "__main__":
    main()
