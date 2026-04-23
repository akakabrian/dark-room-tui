"""Perf probes. ADR doesn't have a big map buffer or expensive FFI, so
this just validates that the hot paths are comfortably under budget.

Hot paths:
- engine.advance(dt): drives every timer
- engine.collect_income(dt): per-tick worker payouts
- LocationPanel render (text construction)
- StoresPanel render (sorted dict walk + text construction)
- world.move + mask flood fill
"""
from __future__ import annotations

import time

from dark_room_tui.app import DarkRoomApp, LocationPanel, StoresPanel


def bench(name: str, fn, iters: int = 1000) -> None:
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    elapsed = time.perf_counter() - t0
    per = elapsed / iters * 1000
    print(f"  {name:<40} {per:8.3f} ms/iter  ({iters} iters, {elapsed*1000:.0f} ms total)")


def main() -> None:
    app = DarkRoomApp(seed=42)
    # bootstrap into the "mid-game" state
    e = app.engine
    e.stores_set("wood", 500)
    e.stores_set("fur", 200)
    e.stores_set("meat", 200)
    e.stores_set("cured meat", 200)
    e.set("game", "builder", "level", value=4)
    e.set("game", "temperature", value={"value": 4})
    e.set("game", "population", value=30)
    e.set("game", "buildings", value={"hut": 6, "trap": 5, "lodge": 1,
                                       "trading post": 1, "tannery": 1})
    e.set("game", "workers", value={"hunter": 4, "trapper": 2, "tanner": 3})
    app.outside.init()
    app.world.init()
    app.path.init()
    # Outside the Textual lifecycle, compose() hasn't run. Instantiate the
    # panel widgets directly for benchmarking.
    app._location = LocationPanel()
    app._stores = StoresPanel()

    print("Perf — A Dark Room TUI")
    print("-" * 62)
    bench("engine.advance(0.1)", lambda: e.advance(0.1), iters=5000)
    bench("engine.collect_income(0.1)", lambda: e.collect_income(0.1), iters=5000)
    bench("room.available_buildings()", lambda: app.room.available_buildings(), iters=2000)
    bench("outside.num_gatherers()", lambda: app.outside.num_gatherers(), iters=5000)

    # location panel render (returns Text)
    bench("LocationPanel render (room)", lambda: app._location._render_room(app), iters=2000)

    # Enter the world
    e.stores_set("cured meat", 100)
    app.path.increase("cured meat", 20)
    app.path.embark()
    bench("LocationPanel render (world)", lambda: app._location._render_world(app), iters=500)
    bench("world.move roundtrip", _move_roundtrip(app), iters=500)
    bench("StoresPanel render",
          lambda: app._stores.build_text(app.engine, app.outside), iters=1000)


def _move_roundtrip(app: DarkRoomApp):
    # cycle through moves so we don't keep drifting off map
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    idx = {"i": 0}

    def step():
        dx, dy = directions[idx["i"] % 4]
        idx["i"] += 1
        app.world.move(dx, dy)
    return step


if __name__ == "__main__":
    main()
