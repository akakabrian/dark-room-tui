"""Deterministic scheduler + state manager — the Python port of

  vendor/adarkroom/script/engine.js
  vendor/adarkroom/script/state_manager.js

Everything in the game talks to an `Engine` instance: timers, RNG,
notifications, and the `state` dict. No jQuery, no DOM — state changes
publish events through `on()` / `emit()` so the TUI can subscribe.
"""
from __future__ import annotations

import heapq
import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# --- notification channel ---------------------------------------------------


@dataclass
class Notification:
    """A message that lands in the event log.

    `module` is a short tag ("room", "outside", "path", "world", ...) so
    the log can prefix / color per location.  If `module` is None, it's a
    global notification (used by world events crossing locations).
    """

    module: str | None
    text: str


# --- scheduler --------------------------------------------------------------


@dataclass(order=True)
class _Scheduled:
    """Priority-queue entry (sortable by due_time, then insertion order)."""

    due_time: float
    counter: int
    cb: Callable[[], None] = field(compare=False)
    cancelled: bool = field(default=False, compare=False)
    tag: str = field(default="", compare=False)


class Engine:
    """The game heart: a clock, an RNG, a state dict, and a pub/sub bus.

    The original ADR uses setTimeout for ~everything (fire cooldown, builder
    state, population growth, world travel...).  We collapse all of that
    into `advance(dt)` driving a single priority queue, so tests can do
    `engine.advance(600)` and run ten minutes of game time instantly.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.time = 0.0
        self.rng = random.Random(seed)
        self._queue: list[_Scheduled] = []
        self._counter = itertools.count()
        self._subs: dict[str, list[Callable[..., None]]] = {}

        # Top-level state — same shape as the JS `$SM` store. Keeping the
        # same keys as the JS source makes event/logic porting line-by-line.
        self.state: dict[str, Any] = {
            "features": {"location": {}, "stores": {}},
            "stores": {},
            "game": {
                "fire": {"value": 0},
                "temperature": {"value": 0},
                "builder": {"level": -1},
                "buildings": {},
                "population": 0,
                "workers": {},
                "outside": {},
                "world": {},
                "path": {},
                "thieves": None,
            },
            "income": {},
            "playStats": {"start": 0, "play": 0, "total": {"wood": 0}},
            "character": {},
        }

        # Notification log (bounded — UI reads the tail).
        self.log: list[Notification] = []

    # ------------ pub/sub -------------------------------------------------

    def on(self, event: str, cb: Callable[..., None]) -> None:
        self._subs.setdefault(event, []).append(cb)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        for cb in list(self._subs.get(event, ())):
            cb(*args, **kwargs)

    # ------------ scheduling ---------------------------------------------

    def set_timeout(
        self,
        cb: Callable[[], None],
        delay: float,
        tag: str = "",
    ) -> _Scheduled:
        """Schedule `cb` to fire after `delay` seconds of game time."""
        entry = _Scheduled(self.time + delay, next(self._counter), cb, tag=tag)
        heapq.heappush(self._queue, entry)
        return entry

    def clear_timeout(self, entry: _Scheduled | None) -> None:
        if entry is not None:
            entry.cancelled = True

    def advance(self, dt: float) -> None:
        """Advance game time by `dt` seconds, firing every due timer.

        Timers scheduled *by* other timers during this call are picked up
        on subsequent heap pops — no need for a second pass.
        """
        target = self.time + dt
        while self._queue and self._queue[0].due_time <= target:
            entry = heapq.heappop(self._queue)
            if entry.cancelled:
                continue
            self.time = entry.due_time
            entry.cb()
        self.time = target

    # ------------ notifications ------------------------------------------

    def notify(self, module: str | None, text: str, *, noqueue: bool = False) -> None:
        note = Notification(module, text)
        self.log.append(note)
        if len(self.log) > 500:
            del self.log[:100]
        self.emit("notify", note)

    # ------------ state helpers ------------------------------------------
    #
    # These mimic $SM.get/set/add/addM from state_manager.js but use plain
    # nested dict access so the Python is idiomatic.  `_path` lives as a
    # short helper for the less-common dotted gets the JS code uses.

    def get(self, *path: str, default: Any = None) -> Any:
        cur: Any = self.state
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def set(self, *path: str, value: Any) -> None:
        cur: Any = self.state
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = value
        self.emit("stateUpdate", path, value)

    def add(self, *path: str, amount: float) -> float:
        current = self.get(*path, default=0) or 0
        new_val = current + amount
        self.set(*path, value=new_val)
        return new_val

    def stores_add(self, name: str, amount: float) -> float:
        """Common path: mutate a stores entry, emit events."""
        cur = self.state.setdefault("stores", {})
        cur[name] = (cur.get(name) or 0) + amount
        if cur[name] < 0:
            cur[name] = 0
        self.emit("stores_changed", name, cur[name])
        return cur[name]

    def stores_get(self, name: str) -> float:
        return (self.state.get("stores", {}) or {}).get(name, 0) or 0

    def stores_set(self, name: str, value: float) -> None:
        self.state.setdefault("stores", {})[name] = value
        self.emit("stores_changed", name, value)

    def stores_addM(self, deltas: dict[str, float]) -> None:
        """Batch stores mutation — single event after all applied."""
        cur = self.state.setdefault("stores", {})
        for k, v in deltas.items():
            cur[k] = max(0, (cur.get(k) or 0) + v)
        self.emit("stores_bulk_changed", deltas)

    def has_features_location(self, name: str) -> bool:
        return bool(self.get("features", "location", name, default=False))

    def set_income(self, source: str, payload: dict) -> None:
        self.state.setdefault("income", {})[source] = payload
        self.emit("income_changed", source)

    def clear_income(self, source: str) -> None:
        income = self.state.setdefault("income", {})
        income.pop(source, None)
        self.emit("income_changed", source)

    # ------------ periodic income tick -----------------------------------
    #
    # JS $SM.collectIncome fires every second and distributes worker output.
    # We model the same: each income source has a `delay` (seconds between
    # payouts) and a `stores` dict of deltas-per-payout.  We track a
    # per-source accumulator and pay out when it reaches the delay.

    def collect_income(self, dt: float) -> None:
        income = self.state.get("income", {}) or {}
        acc = self.state.setdefault("_income_acc", {})
        for source, payload in list(income.items()):
            delay = payload.get("delay", 10)
            stores = payload.get("stores", {}) or {}
            acc[source] = acc.get(source, 0.0) + dt
            while acc[source] >= delay:
                acc[source] -= delay
                # Check we can afford costs (negative entries).
                can_pay = True
                for s, d in stores.items():
                    if d < 0 and self.stores_get(s) + d < 0:
                        can_pay = False
                        break
                if can_pay:
                    self.stores_addM({k: v for k, v in stores.items()})
