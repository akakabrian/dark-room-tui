"""Room module — port of vendor/adarkroom/script/room.js.

Core mechanics:
  - Fire levels Dead/Smoldering/Flickering/Burning/Roaring.
  - Room temperature trails fire by 30 s; fire cools every 5 min.
  - Builder arrives after first stoke, progresses through 5 states,
    becomes the player's helper at state 4.
  - Craftables: wood tools → workshop → metal gear.
  - TradeGoods: fur → scales/teeth/iron/coal/steel at trading post.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Union

if TYPE_CHECKING:
    from .engine import Engine


CostSpec = Union[dict[str, int], Callable[["Engine"], dict[str, int]]]


FIRE_COOL_DELAY = 5 * 60.0
ROOM_WARM_DELAY = 30.0
BUILDER_STATE_DELAY = 30.0
STOKE_COOLDOWN = 10.0
NEED_WOOD_DELAY = 15.0

FIRE_NAMES = ["dead", "smoldering", "flickering", "burning", "roaring"]
TEMP_NAMES = ["freezing", "cold", "mild", "warm", "hot"]


@dataclass
class Craftable:
    name: str
    type: str  # building | weapon | upgrade | tool | good
    cost: CostSpec  # dict[str, int] OR callable(engine) -> dict
    maximum: int = 0  # 0 = unlimited (actually JS uses no maximum field)
    available_msg: str = ""
    build_msg: str = ""
    max_msg: str = ""


def _cost(engine: "Engine", craft: Craftable) -> dict[str, int]:
    c = craft.cost
    if callable(c):
        return c(engine)
    return dict(c)


def _trap_cost(engine: "Engine") -> dict[str, int]:
    n = engine.get("game", "buildings", default={}).get("trap", 0) or 0
    return {"wood": 10 + n * 10}


def _hut_cost(engine: "Engine") -> dict[str, int]:
    n = engine.get("game", "buildings", default={}).get("hut", 0) or 0
    return {"wood": 100 + n * 50}


CRAFTABLES: dict[str, Craftable] = {
    "trap":          Craftable("trap", "building", _trap_cost, maximum=10,
                               available_msg="builder says she can make traps to catch any creatures might still be alive out there",
                               build_msg="more traps to catch more creatures",
                               max_msg="more traps won't help now"),
    "cart":          Craftable("cart", "building", {"wood": 30}, maximum=1,
                               available_msg="builder says she can make a cart for carrying wood",
                               build_msg="the rickety cart will carry more wood from the forest"),
    "hut":           Craftable("hut", "building", _hut_cost, maximum=20,
                               available_msg="builder says there are more wanderers. says they'll work, too.",
                               build_msg="builder puts up a hut, out in the forest. says word will get around.",
                               max_msg="no more room for huts."),
    "lodge":         Craftable("lodge", "building", {"wood": 200, "fur": 10, "meat": 5}, maximum=1,
                               available_msg="villagers could help hunt, given the means",
                               build_msg="the hunting lodge stands in the forest, a ways out of town"),
    "trading post":  Craftable("trading post", "building", {"wood": 400, "fur": 100}, maximum=1,
                               available_msg="a trading post would make commerce easier",
                               build_msg="now the nomads have a place to set up shop, they might stick around a while"),
    "tannery":       Craftable("tannery", "building", {"wood": 500, "fur": 50}, maximum=1,
                               available_msg="builder says leather could be useful. says the villagers could make it.",
                               build_msg="tannery goes up quick, on the edge of the village"),
    "smokehouse":    Craftable("smokehouse", "building", {"wood": 600, "meat": 50}, maximum=1,
                               available_msg="should cure the meat, or it'll spoil. builder says she can fix something up.",
                               build_msg="builder finishes the smokehouse. she looks hungry."),
    "workshop":      Craftable("workshop", "building", {"wood": 800, "leather": 100, "scales": 10}, maximum=1,
                               available_msg="builder says she could make finer things, if she had the tools",
                               build_msg="workshop's finally ready. builder's excited to get to it"),
    "steelworks":    Craftable("steelworks", "building", {"wood": 1500, "iron": 100, "coal": 100}, maximum=1,
                               available_msg="builder says the villagers could make steel, given the tools",
                               build_msg="a haze falls over the village as the steelworks fires up"),
    "armoury":       Craftable("armoury", "building", {"wood": 3000, "steel": 100, "sulphur": 50}, maximum=1,
                               available_msg="builder says it'd be useful to have a steady source of bullets",
                               build_msg="armoury's done, welcoming back the weapons of the past."),
    "torch":         Craftable("torch", "tool", {"wood": 1, "cloth": 1},
                               build_msg="a torch to keep the dark away"),
    "waterskin":     Craftable("waterskin", "upgrade", {"leather": 50}, maximum=1,
                               build_msg="this waterskin'll hold a bit of water, at least"),
    "cask":          Craftable("cask", "upgrade", {"leather": 100, "iron": 20}, maximum=1,
                               build_msg="the cask holds enough water for longer expeditions"),
    "water tank":    Craftable("water tank", "upgrade", {"iron": 100, "steel": 50}, maximum=1,
                               build_msg="never go thirsty again"),
    "bone spear":    Craftable("bone spear", "weapon", {"wood": 100, "teeth": 5},
                               build_msg="this spear's not elegant, but it's pretty good at stabbing"),
    "rucksack":      Craftable("rucksack", "upgrade", {"leather": 200}, maximum=1,
                               build_msg="carrying more means longer expeditions to the wilds"),
    "wagon":         Craftable("wagon", "upgrade", {"wood": 500, "iron": 100}, maximum=1,
                               build_msg="the wagon can carry a lot of supplies"),
    "convoy":        Craftable("convoy", "upgrade", {"wood": 1000, "iron": 200, "steel": 100}, maximum=1,
                               build_msg="the convoy can haul mostly everything"),
    "l armour":      Craftable("l armour", "upgrade", {"leather": 200, "scales": 20}, maximum=1,
                               build_msg="leather's not strong. better than rags, though."),
    "i armour":      Craftable("i armour", "upgrade", {"leather": 200, "iron": 100}, maximum=1,
                               build_msg="iron's stronger than leather"),
    "s armour":      Craftable("s armour", "upgrade", {"leather": 200, "steel": 100}, maximum=1,
                               build_msg="steel's stronger than iron"),
    "iron sword":    Craftable("iron sword", "weapon", {"wood": 200, "leather": 50, "iron": 20},
                               build_msg="sword is sharp. good protection out in the wilds."),
    "steel sword":   Craftable("steel sword", "weapon", {"wood": 500, "leather": 100, "steel": 20},
                               build_msg="the steel is strong, and the blade true."),
    "rifle":         Craftable("rifle", "weapon", {"wood": 200, "steel": 50, "sulphur": 50},
                               build_msg="black powder and bullets, like the old days."),
}


TRADE_GOODS: dict[str, Craftable] = {
    "scales":      Craftable("scales",      "good",    {"fur": 150}),
    "teeth":       Craftable("teeth",       "good",    {"fur": 300}),
    "iron":        Craftable("iron",        "good",    {"fur": 150, "scales": 50}),
    "coal":        Craftable("coal",        "good",    {"fur": 200, "teeth": 50}),
    "steel":       Craftable("steel",       "good",    {"fur": 300, "scales": 50, "teeth": 50}),
    "medicine":    Craftable("medicine",    "good",    {"scales": 50, "teeth": 30}),
    "bullets":     Craftable("bullets",     "good",    {"scales": 10}),
    "energy cell": Craftable("energy cell", "good",    {"scales": 10, "teeth": 10}),
    "bolas":       Craftable("bolas",       "weapon",  {"teeth": 10}),
    "grenade":     Craftable("grenade",     "weapon",  {"scales": 100, "teeth": 50}),
    "bayonet":     Craftable("bayonet",     "weapon",  {"scales": 500, "teeth": 250}),
    "alien alloy": Craftable("alien alloy", "good",    {"fur": 1500, "scales": 750, "teeth": 300}),
    "compass":     Craftable("compass",     "special", {"fur": 400, "scales": 20, "teeth": 10}, maximum=1),
}


class Room:
    """State machine for the dark/firelit room.

    Holds timers on the engine; the UI calls `light_fire`, `stoke_fire`,
    `build(thing)`, `buy(thing)` and reads back state.  All external
    effects (notifications, state writes) go through the engine.
    """

    def __init__(self, engine: "Engine") -> None:
        self.e = engine
        self._fire_timer = None
        self._temp_timer = None
        self._builder_timer = None
        self.last_light_time = -1e9
        self.last_stoke_time = -1e9

    def init(self) -> None:
        e = self.e
        if e.get("features", "location", "room") is None:
            e.set("features", "location", "room", value=True)
            e.set("game", "builder", "level", value=-1)

        # fire/temp default to 0 on fresh game
        if e.get("game", "fire", default=None) is None or e.get("game", "fire", "value") is None:
            e.set("game", "fire", value={"value": 0})
        if e.get("game", "temperature", default=None) is None or e.get("game", "temperature", "value") is None:
            e.set("game", "temperature", value={"value": 0})

        self._fire_timer = e.set_timeout(self._cool_fire, FIRE_COOL_DELAY, tag="fire")
        self._temp_timer = e.set_timeout(self._adjust_temp, ROOM_WARM_DELAY, tag="temp")

        if 0 <= e.get("game", "builder", "level") < 3:
            self._builder_timer = e.set_timeout(
                self._update_builder_state, BUILDER_STATE_DELAY, tag="builder"
            )

        e.notify("room", f"the room is {TEMP_NAMES[e.get('game', 'temperature', 'value')]}")
        e.notify("room", f"the fire is {FIRE_NAMES[e.get('game', 'fire', 'value')]}")

    # --- public actions --------------------------------------------------

    def can_light(self) -> bool:
        return (self.e.time - self.last_light_time) >= STOKE_COOLDOWN

    def can_stoke(self) -> bool:
        return (self.e.time - self.last_stoke_time) >= STOKE_COOLDOWN

    def light_fire(self) -> bool:
        """Light the fire from dead → Burning (3). Costs 5 wood."""
        e = self.e
        if not self.can_light():
            return False
        wood = e.stores_get("wood")
        if wood < 5:
            e.notify("room", "not enough wood to get the fire going")
            return False
        e.stores_add("wood", -5)
        e.set("game", "fire", value={"value": 3})  # Burning
        self.last_light_time = e.time
        self.last_stoke_time = e.time
        self._on_fire_change()
        e.emit("sound", "lightFire")
        return True

    def stoke_fire(self) -> bool:
        e = self.e
        if not self.can_stoke():
            return False
        wood = e.stores_get("wood")
        if wood <= 0:
            e.notify("room", "the wood has run out")
            return False
        e.stores_add("wood", -1)
        cur = e.get("game", "fire", "value")
        if cur < 4:
            e.set("game", "fire", value={"value": cur + 1})
        self.last_stoke_time = e.time
        self._on_fire_change()
        e.emit("sound", "stokeFire")
        return True

    def build(self, thing: str) -> bool:
        """Build/craft one of `thing`. Returns True on success."""
        e = self.e
        if e.get("game", "temperature", "value") <= 1:  # Cold
            e.notify("room", "builder just shivers")
            return False
        craft = CRAFTABLES.get(thing)
        if craft is None:
            return False
        # check max
        if craft.type == "building":
            n = e.get("game", "buildings", default={}).get(thing, 0) or 0
        else:
            n = int(e.stores_get(thing))
        if craft.maximum and n + 1 > craft.maximum:
            return False
        cost = _cost(e, craft)
        for k, v in cost.items():
            if e.stores_get(k) < v:
                e.notify("room", f"not enough {k}")
                return False
        # pay
        for k, v in cost.items():
            e.stores_add(k, -v)
        # receive
        if craft.type == "building":
            b = e.state.setdefault("game", {}).setdefault("buildings", {})
            b[thing] = (b.get(thing) or 0) + 1
            e.emit("buildings_changed", thing, b[thing])
        else:
            e.stores_add(thing, 1)
        if craft.build_msg:
            e.notify("room", craft.build_msg)
        e.emit("sound", "build" if craft.type == "building" else "craft")
        # workshop unlocks crafting
        if thing == "workshop":
            e.emit("workshop_built")
        if thing == "trading post":
            e.emit("trading_post_built")
        if thing == "lodge":
            e.emit("lodge_built")
        return True

    def buy(self, thing: str) -> bool:
        e = self.e
        good = TRADE_GOODS.get(thing)
        if good is None:
            return False
        n = int(e.stores_get(thing))
        if good.maximum and n + 1 > good.maximum:
            return False
        cost = _cost(e, good)
        for k, v in cost.items():
            if e.stores_get(k) < v:
                e.notify("room", f"not enough {k}")
                return False
        for k, v in cost.items():
            e.stores_add(k, -v)
        e.stores_add(thing, 1)
        e.emit("sound", "buy")
        return True

    # --- queries for UI --------------------------------------------------

    def fire_name(self) -> str:
        return FIRE_NAMES[self.e.get("game", "fire", "value")]

    def temp_name(self) -> str:
        return TEMP_NAMES[self.e.get("game", "temperature", "value")]

    def title(self) -> str:
        return "A Dark Room" if self.e.get("game", "fire", "value") < 2 else "A Firelit Room"

    def available_buildings(self) -> list[str]:
        """Craftables whose buttons are currently shown (mirrors
        `craftUnlocked` in room.js)."""
        e = self.e
        out: list[str] = []
        if e.get("game", "builder", "level", default=-1) < 4:
            return out
        has_workshop = (e.get("game", "buildings", default={}).get("workshop", 0) or 0) > 0
        for name, c in CRAFTABLES.items():
            if self._needs_workshop(c.type) and not has_workshop:
                continue
            # already built at least one → always show
            if c.type == "building":
                if (e.get("game", "buildings", default={}).get(name, 0) or 0) > 0:
                    out.append(name)
                    continue
            elif int(e.stores_get(name)) > 0:
                out.append(name)
                continue
            cost = _cost(e, c)
            # need half the wood AND to have seen every component
            if e.stores_get("wood") < cost.get("wood", 0) * 0.5:
                continue
            seen = True
            for k in cost:
                if e.stores_get(k) <= 0 and k != "wood":
                    # wait until the player has even touched the material
                    if e.get("stores", default={}).get(k) is None:
                        seen = False
                        break
            if seen:
                out.append(name)
        return out

    def available_trade(self) -> list[str]:
        e = self.e
        if (e.get("game", "buildings", default={}).get("trading post", 0) or 0) == 0:
            return []
        return list(TRADE_GOODS.keys())

    # --- timers ----------------------------------------------------------

    def _cool_fire(self) -> None:
        e = self.e
        cur = e.get("game", "fire", "value")
        wood = e.stores_get("wood")
        if cur <= 2 and e.get("game", "builder", "level") > 3 and wood > 0:
            e.notify("room", "builder stokes the fire")
            e.stores_add("wood", -1)
            cur = min(4, cur + 1)
            e.set("game", "fire", value={"value": cur})
        if cur > 0:
            e.set("game", "fire", value={"value": cur - 1})
            self._on_fire_change()
        # re-schedule regardless — fire may have just been re-lit
        self._fire_timer = e.set_timeout(self._cool_fire, FIRE_COOL_DELAY, tag="fire")

    def _adjust_temp(self) -> None:
        e = self.e
        t = e.get("game", "temperature", "value")
        f = e.get("game", "fire", "value")
        old = t
        if t > 0 and t > f:
            t -= 1
        if t < 4 and t < f:
            t += 1
        if t != old:
            e.set("game", "temperature", value={"value": t})
            e.notify("room", f"the room is {TEMP_NAMES[t]}")
        self._temp_timer = e.set_timeout(self._adjust_temp, ROOM_WARM_DELAY, tag="temp")

    def _on_fire_change(self) -> None:
        e = self.e
        f = e.get("game", "fire", "value")
        e.notify("room", f"the fire is {FIRE_NAMES[f]}", noqueue=True)
        if f > 1 and e.get("game", "builder", "level") < 0:
            e.set("game", "builder", "level", value=0)
            e.notify("room", "the light from the fire spills from the windows, out into the dark")
            self._builder_timer = e.set_timeout(
                self._update_builder_state, BUILDER_STATE_DELAY, tag="builder"
            )
        e.clear_timeout(self._fire_timer)
        self._fire_timer = e.set_timeout(self._cool_fire, FIRE_COOL_DELAY, tag="fire")

    def _update_builder_state(self) -> None:
        e = self.e
        level = e.get("game", "builder", "level")
        if level == 0:
            e.notify("room", "a ragged stranger stumbles through the door and collapses in the corner")
            e.set("game", "builder", "level", value=1)
            e.set_timeout(self._unlock_forest, NEED_WOOD_DELAY, tag="unlock_forest")
        elif level < 3 and e.get("game", "temperature", "value") >= 3:  # Warm
            if level == 1:
                e.notify("room", "the stranger shivers, and mumbles quietly. her words are unintelligible.")
            elif level == 2:
                e.notify("room", "the stranger in the corner stops shivering. her breathing calms.")
            e.set("game", "builder", "level", value=level + 1)
        if e.get("game", "builder", "level") < 3:
            self._builder_timer = e.set_timeout(
                self._update_builder_state, BUILDER_STATE_DELAY, tag="builder"
            )
        elif e.get("game", "builder", "level") == 3:
            # transition to helper on arrival — for CLI, auto-promote
            self._promote_builder()

    def _promote_builder(self) -> None:
        e = self.e
        e.set("game", "builder", "level", value=4)
        e.set_income("builder", {"delay": 10, "stores": {"wood": 2}})
        e.notify("room", "the stranger is standing by the fire. she says she can help. says she builds things.")
        e.emit("builder_helping")

    def _unlock_forest(self) -> None:
        e = self.e
        # JS sets wood to 4 on unlock; "running out" flavor message.
        e.stores_set("wood", 4)
        e.notify("room", "the wind howls outside")
        e.notify("room", "the wood is running out")
        e.emit("unlock_forest")

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _needs_workshop(t: str) -> bool:
        return t in ("weapon", "upgrade", "tool")
