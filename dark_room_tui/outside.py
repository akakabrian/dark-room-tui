"""Outside module — port of vendor/adarkroom/script/outside.js.

Villagers, huts, gathering wood, checking traps, worker assignments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Engine


GATHER_DELAY = 60.0
TRAPS_DELAY = 90.0
POP_DELAY_MIN = 0.5 * 60.0
POP_DELAY_MAX = 3.0 * 60.0
HUT_ROOM = 4


INCOME: dict[str, dict] = {
    "gatherer":      {"delay": 10, "stores": {"wood": 1}},
    "hunter":        {"delay": 10, "stores": {"fur": 0.5, "meat": 0.5}},
    "trapper":       {"delay": 10, "stores": {"meat": -1, "bait": 1}},
    "tanner":        {"delay": 10, "stores": {"fur": -5, "leather": 1}},
    "charcutier":    {"delay": 10, "stores": {"meat": -5, "wood": -5, "cured meat": 1}},
    "iron miner":    {"delay": 10, "stores": {"cured meat": -1, "iron": 1}},
    "coal miner":    {"delay": 10, "stores": {"cured meat": -1, "coal": 1}},
    "sulphur miner": {"delay": 10, "stores": {"cured meat": -1, "sulphur": 1}},
    "steelworker":   {"delay": 10, "stores": {"iron": -1, "coal": -1, "steel": 1}},
    "armourer":      {"delay": 10, "stores": {"steel": -1, "sulphur": -1, "bullets": 1}},
}

TRAP_DROPS = [
    (0.5,   "fur",    "scraps of fur"),
    (0.75,  "meat",   "bits of meat"),
    (0.85,  "scales", "strange scales"),
    (0.93,  "teeth",  "scattered teeth"),
    (0.995, "cloth",  "tattered cloth"),
    (1.0,   "charm",  "a crudely made charm"),
]


JOB_MAP: dict[str, list[str]] = {
    "lodge":        ["hunter", "trapper"],
    "tannery":      ["tanner"],
    "smokehouse":   ["charcutier"],
    "iron mine":    ["iron miner"],
    "coal mine":    ["coal miner"],
    "sulphur mine": ["sulphur miner"],
    "steelworks":   ["steelworker"],
    "armoury":      ["armourer"],
}


class Outside:
    def __init__(self, engine: "Engine") -> None:
        self.e = engine
        self.last_gather_time = -1e9
        self.last_traps_time = -1e9
        self._pop_timer = None

    def init(self) -> None:
        e = self.e
        if e.get("features", "location", "outside") is None:
            e.set("features", "location", "outside", value=True)
        if e.get("game", "buildings", default=None) is None:
            e.set("game", "buildings", value={})
        if e.get("game", "population", default=None) is None:
            e.set("game", "population", value=0)
        if e.get("game", "workers", default=None) is None:
            e.set("game", "workers", value={})

        # subscribe to building changes so worker slots get created
        e.on("buildings_changed", self._on_building_built)
        e.on("lodge_built", lambda: self._ensure_workers_for("lodge"))

        if not e.get("game", "outside", "seenForest"):
            e.notify("outside", "the sky is grey and the wind blows relentlessly")
            e.set("game", "outside", "seenForest", value=True)

    # --- actions ---------------------------------------------------------

    def can_gather(self) -> bool:
        return (self.e.time - self.last_gather_time) >= GATHER_DELAY

    def can_check_traps(self) -> bool:
        return (self.e.time - self.last_traps_time) >= TRAPS_DELAY

    def gather_wood(self) -> bool:
        e = self.e
        if not self.can_gather():
            return False
        e.notify("outside", "dry brush and dead branches litter the forest floor")
        amt = 50 if (e.get("game", "buildings", default={}).get("cart", 0) or 0) > 0 else 10
        e.stores_add("wood", amt)
        self.last_gather_time = e.time
        e.emit("sound", "gatherWood")
        return True

    def check_traps(self) -> bool:
        e = self.e
        if not self.can_check_traps():
            return False
        num_traps = e.get("game", "buildings", default={}).get("trap", 0) or 0
        if num_traps <= 0:
            return False
        num_bait = int(e.stores_get("bait"))
        num_drops = num_traps + (num_bait if num_bait < num_traps else num_traps)
        drops: dict[str, int] = {}
        msgs: list[str] = []
        for _ in range(num_drops):
            roll = e.rng.random()
            for upper, name, msg in TRAP_DROPS:
                if roll < upper:
                    if name not in drops:
                        drops[name] = 0
                        msgs.append(msg)
                    drops[name] += 1
                    break
        bait_used = min(num_bait, num_traps)
        if bait_used > 0:
            drops["bait"] = drops.get("bait", 0) - bait_used
        if msgs:
            s = "the traps contain "
            for i, m in enumerate(msgs):
                if len(msgs) > 1 and 0 < i < len(msgs) - 1:
                    s += ", "
                elif len(msgs) > 1 and i == len(msgs) - 1:
                    s += " and "
                s += m
            e.notify("outside", s)
        e.stores_addM(drops)
        self.last_traps_time = e.time
        e.emit("sound", "checkTraps")
        return True

    # --- workers ---------------------------------------------------------

    def max_population(self) -> int:
        huts = self.e.get("game", "buildings", default={}).get("hut", 0) or 0
        return huts * HUT_ROOM

    def num_gatherers(self) -> int:
        pop = self.e.get("game", "population") or 0
        workers = self.e.get("game", "workers", default={}) or {}
        return pop - sum(int(v) for v in workers.values())

    def increase_worker(self, job: str, amount: int = 1) -> None:
        avail = self.num_gatherers()
        if avail <= 0:
            return
        delta = min(avail, amount)
        w = self.e.state.setdefault("game", {}).setdefault("workers", {})
        w[job] = (w.get(job) or 0) + delta
        self._rebuild_income()
        self.e.emit("workers_changed", job, w[job])

    def decrease_worker(self, job: str, amount: int = 1) -> None:
        w = self.e.state.setdefault("game", {}).setdefault("workers", {})
        cur = w.get(job) or 0
        if cur <= 0:
            return
        delta = min(cur, amount)
        w[job] = cur - delta
        self._rebuild_income()
        self.e.emit("workers_changed", job, w[job])

    def increase_population(self) -> None:
        e = self.e
        space = self.max_population() - (e.get("game", "population") or 0)
        if space > 0:
            num = int(e.rng.random() * (space / 2) + space / 2)
            if num == 0:
                num = 1
            if num == 1:
                e.notify(None, "a stranger arrives in the night")
            elif num < 5:
                e.notify(None, "a weathered family takes up in one of the huts.")
            elif num < 10:
                e.notify(None, "a small group arrives, all dust and bones.")
            elif num < 30:
                e.notify(None, "a convoy lurches in, equal parts worry and hope.")
            else:
                e.notify(None, "the town's booming. word does get around.")
            e.add("game", "population", amount=num)
            self._rebuild_income()
        self.schedule_pop_increase()

    def schedule_pop_increase(self) -> None:
        e = self.e
        delay = POP_DELAY_MIN + e.rng.random() * (POP_DELAY_MAX - POP_DELAY_MIN)
        self._pop_timer = e.set_timeout(self.increase_population, delay, tag="pop")

    def kill_villagers(self, num: int) -> None:
        e = self.e
        e.add("game", "population", amount=-num)
        if (e.get("game", "population") or 0) < 0:
            e.set("game", "population", value=0)
        remaining = self.num_gatherers()
        if remaining < 0:
            gap = -remaining
            for k, v in list((e.get("game", "workers") or {}).items()):
                if v < gap:
                    gap -= v
                    e.set("game", "workers", k, value=0)
                else:
                    e.set("game", "workers", k, value=v - gap)
                    break
        self._rebuild_income()

    def title(self) -> str:
        n = self.e.get("game", "buildings", default={}).get("hut", 0) or 0
        if n == 0:
            return "A Silent Forest"
        if n == 1:
            return "A Lonely Hut"
        if n <= 4:
            return "A Tiny Village"
        if n <= 8:
            return "A Modest Village"
        if n <= 14:
            return "A Large Village"
        return "A Raucous Village"

    # --- hooks -----------------------------------------------------------

    def _on_building_built(self, name: str, _count: int) -> None:
        # Adjust income / worker slots when certain buildings go up.
        self._ensure_workers_for(name)
        if name == "hut" and self._pop_timer is None:
            self.schedule_pop_increase()

    def _ensure_workers_for(self, name: str) -> None:
        jobs = JOB_MAP.get(name)
        if not jobs:
            return
        w = self.e.state.setdefault("game", {}).setdefault("workers", {})
        added = False
        for j in jobs:
            if j not in w:
                w[j] = 0
                added = True
        if added:
            self._rebuild_income()

    def _rebuild_income(self) -> None:
        """Recompute income multipliers from worker counts."""
        e = self.e
        workers = e.get("game", "workers", default={}) or {}
        # gatherer income = num_gatherers * per-gatherer-delta
        ng = self.num_gatherers()
        if ng > 0:
            base = INCOME["gatherer"]
            e.set_income("gatherer", {
                "delay": base["delay"],
                "stores": {k: v * ng for k, v in base["stores"].items()},
            })
        else:
            e.clear_income("gatherer")
        for job, n in workers.items():
            if job not in INCOME:
                continue
            if n <= 0:
                e.clear_income(job)
                continue
            base = INCOME[job]
            e.set_income(job, {
                "delay": base["delay"],
                "stores": {k: v * n for k, v in base["stores"].items()},
            })
