"""Path module — outfitting + embark.

Ports vendor/adarkroom/script/path.js (outfit editing, bag capacity) and
the world.js `Weapons` table (used by combat).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .engine import Engine


DEFAULT_BAG_SPACE = 10

WEIGHTS: dict[str, float] = {
    "bone spear": 2,
    "iron sword": 3,
    "steel sword": 5,
    "rifle": 5,
    "laser rifle": 5,
    "plasma rifle": 5,
    "bullets": 0.1,
    "energy cell": 0.2,
    "bolas": 0.5,
}


@dataclass
class Weapon:
    verb: str
    type: str
    damage: int | str  # int damage, or "stun"
    cooldown: int
    cost: dict = None  # type: ignore

    def __post_init__(self) -> None:
        if self.cost is None:
            self.cost = {}


WEAPONS: dict[str, Weapon] = {
    "fists":        Weapon("punch",        "unarmed", 1, 2),
    "bone spear":   Weapon("stab",         "melee",   2, 2),
    "iron sword":   Weapon("swing",        "melee",   4, 2),
    "steel sword":  Weapon("slash",        "melee",   6, 2),
    "bayonet":      Weapon("thrust",       "melee",   8, 2),
    "rifle":        Weapon("shoot",        "ranged",  5, 1, {"bullets": 1}),
    "laser rifle":  Weapon("blast",        "ranged",  8, 1, {"energy cell": 1}),
    "grenade":      Weapon("lob",          "ranged",  15, 5, {"grenade": 1}),
    "bolas":        Weapon("tangle",       "ranged",  "stun", 15, {"bolas": 1}),
    "plasma rifle": Weapon("disintegrate", "ranged",  12, 1, {"energy cell": 1}),
    "energy blade": Weapon("slice",        "melee",   10, 2),
    "disruptor":    Weapon("stun",         "ranged",  "stun", 15),
}


# Items eligible for the embark outfit (consumables + weapons + a few goods).
OUTFITTABLE = {
    "cured meat", "bullets", "energy cell", "medicine", "bolas", "grenade",
    "torch", "charm",
    # weapons
    "bone spear", "iron sword", "steel sword", "rifle",
    "laser rifle", "plasma rifle", "bayonet", "energy blade", "disruptor",
}


class Path:
    """Outfitting screen + embark action.

    The player edits `outfit` (a dict of item→count) by +/- before
    embarking.  When `embark` is called, items are moved from stores into
    the expedition's outfit and the world is entered.
    """

    def __init__(self, engine: "Engine", world) -> None:  # world: .world.World
        self.e = engine
        self.world = world
        self.outfit: dict[str, int] = {}

    def init(self) -> None:
        e = self.e
        if e.get("features", "location", "path") is None:
            e.set("features", "location", "path", value=True)
            e.notify("path", "the compass points into the dark")

    # ---- bag capacity ----------------------------------------------------

    def capacity(self) -> int:
        s = self.e.stores_get
        if s("convoy") > 0:
            return DEFAULT_BAG_SPACE + 60
        if s("wagon") > 0:
            return DEFAULT_BAG_SPACE + 30
        if s("rucksack") > 0:
            return DEFAULT_BAG_SPACE + 10
        return DEFAULT_BAG_SPACE

    def weight(self, thing: str) -> float:
        return WEIGHTS.get(thing, 1.0)

    def free_space(self) -> float:
        used = sum(n * self.weight(k) for k, n in self.outfit.items())
        return self.capacity() - used

    # ---- outfit editing --------------------------------------------------

    def outfittable(self) -> list[str]:
        """Items the player currently has in stores that are eligible."""
        e = self.e
        stores = e.state.get("stores", {}) or {}
        return sorted(k for k in OUTFITTABLE
                      if int(stores.get(k, 0) or 0) > 0 or self.outfit.get(k, 0) > 0)

    def increase(self, thing: str, n: int = 1) -> bool:
        """Move `n` of `thing` from stores into outfit. Respects weight."""
        e = self.e
        if thing not in OUTFITTABLE:
            return False
        stores = e.stores_get(thing)
        if stores <= 0:
            return False
        w = self.weight(thing)
        # cap by free space and by stores
        can_take = int(min(n, stores, self.free_space() // w if w > 0 else n))
        if can_take <= 0:
            return False
        e.stores_add(thing, -can_take)
        self.outfit[thing] = self.outfit.get(thing, 0) + can_take
        return True

    def decrease(self, thing: str, n: int = 1) -> bool:
        cur = self.outfit.get(thing, 0)
        if cur <= 0:
            return False
        give = min(cur, n)
        self.outfit[thing] = cur - give
        self.e.stores_add(thing, give)
        if self.outfit[thing] == 0:
            del self.outfit[thing]
        return True

    # ---- embark ---------------------------------------------------------

    def embark(self) -> bool:
        """Begin an expedition. Requires at least 1 cured meat in outfit."""
        if (self.outfit.get("cured meat", 0) or 0) <= 0:
            self.e.notify("path", "need cured meat to last the journey")
            return False
        self.world.on_arrival(dict(self.outfit))
        # outfit stays attached to world; path view clears its copy
        self.outfit = {}
        self.e.emit("sound", "embark")
        return True
