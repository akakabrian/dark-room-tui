"""QA harness — drive the TUI with Textual's Pilot and make assertions.

Usage:
  python -m tests.qa            # run every scenario
  python -m tests.qa trap       # run scenarios with 'trap' in the name

Each scenario gets a fresh `DarkRoomApp(seed=42)` so RNG is deterministic.
Results are printed as PASS/FAIL with tracebacks for fails, and an SVG of
the final screen is saved to `tests/out/<name>.(PASS|FAIL).svg`.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from dark_room_tui.app import DarkRoomApp


OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[DarkRoomApp, object], Awaitable[None]]


SCENARIOS: list[Scenario] = []


def scenario(name: str):
    def deco(fn):
        SCENARIOS.append(Scenario(name, fn))
        return fn
    return deco


# ---- helpers ---------------------------------------------------------------


async def advance_game(app: DarkRoomApp, pilot, seconds: float) -> None:
    """Fast-forward game time (no TUI ticks), then let the UI redraw."""
    app.engine.advance(seconds)
    app.engine.collect_income(seconds)
    await pilot.pause()


def assert_eq(a, b, msg: str = "") -> None:
    if a != b:
        raise AssertionError(f"{msg}: {a!r} != {b!r}")


def assert_gt(a, b, msg: str = "") -> None:
    if not (a > b):
        raise AssertionError(f"{msg}: {a!r} not > {b!r}")


def assert_ge(a, b, msg: str = "") -> None:
    if not (a >= b):
        raise AssertionError(f"{msg}: {a!r} not >= {b!r}")


# ---- scenarios -------------------------------------------------------------


@scenario("mount_clean")
async def _mount_clean(app: DarkRoomApp, pilot) -> None:
    assert app._location is not None
    assert app._stores is not None
    assert app._event_log is not None
    # active default is room
    assert_eq(app.active_location, "room")
    assert_eq(app.room.fire_name(), "dead")


@scenario("light_fire_needs_wood")
async def _light_no_wood(app: DarkRoomApp, pilot) -> None:
    # without seeded wood, light should fail
    app.engine.stores_set("wood", 0)
    ok = app.room.light_fire()
    assert_eq(ok, False, "should not be able to light without wood")


@scenario("light_fire_with_wood")
async def _light_with_wood(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 5)
    await pilot.press("l")
    await pilot.pause()
    assert_eq(app.room.fire_name(), "burning", "fire should be burning")
    assert_eq(app.engine.stores_get("wood"), 0, "wood consumed")


@scenario("stoke_fire_consumes_wood")
async def _stoke(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 10)
    app.room.light_fire()
    # cooldown — fast-forward engine time so stoke is allowed
    app.engine.advance(11)
    start = app.engine.stores_get("wood")
    app.room.stoke_fire()
    assert_eq(app.engine.stores_get("wood"), start - 1, "stoke eats 1 wood")


@scenario("builder_arrives_after_time")
async def _builder(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 5)
    app.room.light_fire()
    # builder starts at level 0, arrives-in-door at 1 after 30s
    await advance_game(app, pilot, 31)
    assert_ge(app.engine.get("game", "builder", "level") or 0, 1, "builder arrived")


@scenario("forest_unlocks_stores_wood")
async def _forest(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 5)
    app.room.light_fire()
    # 30s builder enters, +15s forest unlocks
    await advance_game(app, pilot, 60)
    # wood is set to 4 when forest unlocks
    # since fire still burns and builder hasn't stoked (level < 4), cooling eats wood slowly
    # but unlock_forest sets wood to 4 flat — confirm outside panel exists
    feat = app.engine.get("features", "location", "outside")
    assert_eq(feat, True, "outside unlocked")


@scenario("builder_promotes_and_provides_income")
async def _promote(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 20)
    app.room.light_fire()
    # warm the room (stoke repeatedly to push temp up)
    for _ in range(5):
        app.engine.advance(11)
        app.room.stoke_fire()
    await advance_game(app, pilot, 300)  # long enough to cross levels 1→4
    level = app.engine.get("game", "builder", "level") or 0
    assert_ge(level, 4, "builder promoted to helper")
    income = app.engine.state.get("income") or {}
    assert "builder" in income, "builder income ticking"


@scenario("gather_wood_gives_10")
async def _gather(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 0)
    app.outside.init()
    ok = app.outside.gather_wood()
    assert_eq(ok, True)
    assert_eq(app.engine.stores_get("wood"), 10, "gather gives 10 wood without cart")


@scenario("gather_cooldown_blocks_second")
async def _gather_cd(app: DarkRoomApp, pilot) -> None:
    app.outside.init()
    app.outside.gather_wood()
    ok2 = app.outside.gather_wood()
    assert_eq(ok2, False, "second gather blocked by cooldown")


@scenario("build_trap")
async def _build_trap(app: DarkRoomApp, pilot) -> None:
    e = app.engine
    # push to a state where the room is warm + builder helping
    e.set("game", "builder", "level", value=4)
    e.set("game", "temperature", value={"value": 3})
    e.stores_set("wood", 100)
    ok = app.room.build("trap")
    assert_eq(ok, True, "trap built")
    traps = (e.get("game", "buildings") or {}).get("trap", 0)
    assert_eq(traps, 1)


@scenario("traps_produce_loot")
async def _traps(app: DarkRoomApp, pilot) -> None:
    e = app.engine
    e.set("game", "buildings", "trap", value=5)
    app.outside.init()
    ok = app.outside.check_traps()
    assert_eq(ok, True)
    stores = e.state.get("stores") or {}
    # at least one of fur/meat/scales/teeth/cloth/charm must be > 0
    assert any(stores.get(k, 0) for k in ("fur", "meat", "scales", "teeth", "cloth", "charm")), \
        f"got no trap loot; stores={stores}"


@scenario("villager_population_grows")
async def _pop(app: DarkRoomApp, pilot) -> None:
    e = app.engine
    e.set("game", "buildings", "hut", value=3)  # room for 12
    app.outside.init()
    app.outside.schedule_pop_increase()
    # three cycles of 3 minutes max should spawn people
    await advance_game(app, pilot, 4 * 60)
    pop = e.get("game", "population") or 0
    assert_gt(pop, 0, "villagers arrive")


@scenario("worker_assignment_creates_income")
async def _worker(app: DarkRoomApp, pilot) -> None:
    e = app.engine
    e.set("game", "buildings", "hut", value=5)
    e.set("game", "buildings", "lodge", value=1)
    e.set("game", "population", value=6)
    app.outside.init()
    app.outside._ensure_workers_for("lodge")
    app.outside.increase_worker("hunter", 2)
    assert_eq((e.get("game", "workers") or {}).get("hunter"), 2)
    inc = (e.state.get("income") or {}).get("hunter")
    assert inc is not None, "hunter income present"
    # 2 hunters = +1 fur/sec and +1 meat/sec over a 10s delay
    assert_eq(inc["stores"]["fur"], 1.0)


@scenario("embark_requires_cured_meat")
async def _embark_blocked(app: DarkRoomApp, pilot) -> None:
    app.path.init()
    ok = app.path.embark()
    assert_eq(ok, False, "embark needs cured meat")


@scenario("embark_enters_world")
async def _embark_ok(app: DarkRoomApp, pilot) -> None:
    app.path.init()
    app.world.init()  # gen map
    app.engine.stores_set("cured meat", 5)
    app.path.increase("cured meat", 5)
    ok = app.path.embark()
    assert_eq(ok, True)
    assert app.world.state is not None, "world state live"
    # position at village centre
    assert_eq(app.world.state.cur_pos, [30, 30])


@scenario("world_move_reveals_tiles")
async def _move(app: DarkRoomApp, pilot) -> None:
    app.path.init()
    app.world.init()
    app.engine.stores_set("cured meat", 20)
    app.path.increase("cured meat", 10)
    app.path.embark()
    assert app.world.state is not None
    before = sum(sum(row) for row in app.world.state.mask)
    app.world.move(1, 0)
    assert app.world.state is not None
    after = sum(sum(row) for row in app.world.state.mask)
    assert_gt(after, before, "mask expands on move")


@scenario("world_return_home_revealed")
async def _return(app: DarkRoomApp, pilot) -> None:
    app.path.init()
    app.world.init()
    app.engine.stores_set("cured meat", 20)
    app.path.increase("cured meat", 10)
    app.path.embark()
    for _ in range(3):
        app.world.move(1, 0)
    # commit the expedition back to persistent state
    app.world.go_home()
    assert app.world.state is None, "expedition committed"


@scenario("combat_kills_enemy")
async def _combat(app: DarkRoomApp, pilot) -> None:
    app.path.init()
    app.world.init()
    app.engine.stores_set("cured meat", 20)
    app.path.increase("cured meat", 10)
    app.path.embark()
    from dark_room_tui.world import Enemy, Combat
    enemy = Enemy("dummy", 2, 1, 0.0, {"fur": (1, 1)})
    assert app.world.state is not None
    app.world.state.combat = Combat(enemy=enemy, enemy_hp=enemy.health)
    # hit chance is BASE_HIT_CHANCE 0.8; seeded RNG will land
    app.world.combat_attack("fists")
    app.world.combat_attack("fists")
    assert app.world.state is not None, "should still be alive"
    assert app.world.state.combat is None, "enemy dead"
    assert app.world.outfit.get("fur", 0) >= 1, "loot awarded"


@scenario("ship_unlocks_on_find")
async def _ship_unlock(app: DarkRoomApp, pilot) -> None:
    app.ship.init()
    assert_eq(app.engine.get("features", "location", "spaceShip"), True)


@scenario("ship_liftoff_needs_hull")
async def _liftoff_guard(app: DarkRoomApp, pilot) -> None:
    app.ship.init()
    ok = app.ship.lift_off()
    assert_eq(ok, False, "can't lift off with 0 hull")


@scenario("ship_liftoff_victory")
async def _victory(app: DarkRoomApp, pilot) -> None:
    app.ship.init()
    app.engine.stores_set("alien alloy", 5)
    app.ship.reinforce_hull()
    ok = app.ship.lift_off()
    assert_eq(ok, True, "lifts off")
    assert_eq(app.ship.lifted_off, True)


@scenario("key_binding_1_goes_home")
async def _keybind(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 5)
    app.room.light_fire()
    # unlock outside so binding 2 works
    app.outside.init()
    await pilot.press("2")
    await pilot.pause()
    assert_eq(app.active_location, "outside")
    await pilot.press("1")
    await pilot.pause()
    assert_eq(app.active_location, "room")


@scenario("ui_stores_panel_shows_wood")
async def _stores_render(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 42)
    await pilot.pause()
    app._refresh_ui()
    # StoresPanel.build_text() returns a rich Text directly (no Renderable
    # coercion through Static.render()).
    assert app._stores is not None
    text = app._stores.build_text(app.engine, app.outside).plain
    assert "42" in text, f"stores panel missing '42' in {text!r}"
    assert "wood" in text


@scenario("income_ticks_grow_stores")
async def _income(app: DarkRoomApp, pilot) -> None:
    e = app.engine
    e.set_income("test", {"delay": 1, "stores": {"wood": 3}})
    e.collect_income(5)
    assert_eq(e.stores_get("wood"), 15, "5 seconds of income at 3/tick")


# ---- Stage 6: robustness -------------------------------------------------


@scenario("robust_stoke_with_no_wood")
async def _stoke_no_wood(app: DarkRoomApp, pilot) -> None:
    app.engine.stores_set("wood", 5)
    app.room.light_fire()
    app.engine.stores_set("wood", 0)
    app.engine.advance(11)  # clear cooldown
    ok = app.room.stoke_fire()
    assert_eq(ok, False, "stoke fails cleanly when out of wood")


@scenario("robust_build_without_warm_room")
async def _build_cold(app: DarkRoomApp, pilot) -> None:
    # builder present but room cold → notify, don't crash
    app.engine.set("game", "builder", "level", value=4)
    app.engine.set("game", "temperature", value={"value": 0})
    app.engine.stores_set("wood", 999)
    ok = app.room.build("trap")
    assert_eq(ok, False, "cold room blocks builder")


@scenario("robust_combat_with_empty_outfit")
async def _combat_empty(app: DarkRoomApp, pilot) -> None:
    app.path.init(); app.world.init()
    app.engine.stores_set("cured meat", 5)
    app.path.increase("cured meat", 5)
    app.path.embark()
    from dark_room_tui.world import Combat, Enemy
    enemy = Enemy("test", 1, 1, 0.0, {"fur": (1, 1)})
    assert app.world.state is not None
    app.world.state.combat = Combat(enemy=enemy, enemy_hp=enemy.health)
    app.world.combat_attack("fists")  # no costed weapon needed
    assert app.world.state is not None
    assert app.world.state.combat is None


@scenario("robust_worker_decrease_below_zero")
async def _dec_zero(app: DarkRoomApp, pilot) -> None:
    app.engine.set("game", "buildings", "lodge", value=1)
    app.engine.set("game", "population", value=2)
    app.outside.init()
    app.outside._ensure_workers_for("lodge")
    # decrement beyond zero shouldn't go negative or crash
    app.outside.decrease_worker("hunter", 5)
    assert_eq((app.engine.get("game", "workers") or {}).get("hunter", 0), 0)


@scenario("robust_move_beyond_bounds")
async def _out_of_bounds(app: DarkRoomApp, pilot) -> None:
    app.path.init(); app.world.init()
    app.engine.stores_set("cured meat", 5)
    app.path.increase("cured meat", 5)
    app.path.embark()
    # teleport to an edge and try to step further — should clamp
    from dark_room_tui.world import SIZE
    assert app.world.state is not None
    app.world.state.cur_pos = [SIZE - 1, SIZE - 1]
    app.world.move(1, 0)   # off east
    app.world.move(0, 1)   # off south
    assert app.world.state is not None
    x, y = app.world.state.cur_pos
    assert 0 <= x < SIZE and 0 <= y < SIZE, f"pos clamped, got ({x},{y})"


@scenario("robust_unknown_action_does_not_crash")
async def _unknown(app: DarkRoomApp, pilot) -> None:
    # an unrelated key should be harmless
    await pilot.press("j")
    await pilot.pause()
    assert_eq(app.active_location, "room")


@scenario("robust_stores_panel_with_empty_state")
async def _empty_store(app: DarkRoomApp, pilot) -> None:
    # freshly built app has no stores — build_text must not crash
    assert app._stores is not None
    t = app._stores.build_text(app.engine, app.outside)
    assert "stores" in t.plain


@scenario("robust_location_panel_world_without_state")
async def _world_without(app: DarkRoomApp, pilot) -> None:
    app.active_location = "world"
    assert app._location is not None
    t = app._location._render_world(app)
    assert "not out there" in t.plain, "graceful empty-world render"


@scenario("polish_cooldown_bar_renders")
async def _bar_renders(app: DarkRoomApp, pilot) -> None:
    app.outside.init()
    app.outside.gather_wood()
    app.engine.advance(30)  # halfway through cooldown
    assert app._location is not None
    t = app._location._render_outside(app)
    assert "[" in t.plain and "#" in t.plain, f"bar partial fill, got {t.plain!r}"


@scenario("polish_fire_color_changes_with_level")
async def _fire_color(app: DarkRoomApp, pilot) -> None:
    # cold -> dead
    assert app._location is not None
    t0 = app._location._render_room(app).plain
    app.engine.stores_set("wood", 5)
    app.room.light_fire()
    t1 = app._location._render_room(app).plain
    assert "dead" in t0 and "burning" in t1


@scenario("polish_sound_engine_safe_when_mute")
async def _sound_mute(app: DarkRoomApp, pilot) -> None:
    from dark_room_tui.sound import SoundEngine
    s = SoundEngine(enabled=False)
    s.play("lightFire")  # should not raise
    assert not s.enabled


# ---- runner ---------------------------------------------------------------


async def _run(app: DarkRoomApp, pilot, scn: Scenario) -> tuple[str, bool, str]:
    try:
        await pilot.pause()
        await scn.fn(app, pilot)
        app.save_screenshot(str(OUT_DIR / f"{scn.name}.PASS.svg"))
        return scn.name, True, ""
    except Exception as e:
        tb = traceback.format_exc()
        try:
            app.save_screenshot(str(OUT_DIR / f"{scn.name}.FAIL.svg"))
        except Exception:
            pass
        return scn.name, False, tb


async def _run_scenario(scn: Scenario) -> tuple[str, bool, str]:
    app = DarkRoomApp(seed=42)
    async with app.run_test(size=(120, 40)) as pilot:
        return await _run(app, pilot, scn)


async def _main(pattern: str | None) -> int:
    sel = [s for s in SCENARIOS if pattern is None or pattern in s.name]
    if not sel:
        print(f"no scenarios match {pattern!r}", file=sys.stderr)
        return 2
    passed = failed = 0
    failures: list[tuple[str, str]] = []
    for scn in sel:
        name, ok, err = await _run_scenario(scn)
        if ok:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            failures.append((name, err))
            print(f"  FAIL  {name}")
    print(f"\n{passed} passed, {failed} failed")
    if failures:
        print("\nFailure details")
        print("---------------")
        for name, err in failures:
            print(f"\n[{name}]\n{err}")
    return 0 if failed == 0 else 1


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    return asyncio.run(_main(pattern))


if __name__ == "__main__":
    raise SystemExit(main())
