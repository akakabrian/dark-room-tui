"""World module — port of vendor/adarkroom/script/world.js.

Procedural 61x61 wasteland with sticky terrain, landmarks, fog-of-war,
food/water consumption per move, and simple encounter rolls.

The full events.js combat tree is huge — we include a slimmed setpiece
and encounter system that mirrors the shape (enemy entry → swing loop →
loot) without porting all 200+ flavor events.  The ship landmark is
preserved so the ending reachable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .engine import Engine


RADIUS = 30
SIZE = RADIUS * 2 + 1  # 61
VILLAGE_POS = (RADIUS, RADIUS)

# Tile glyphs — match the JS table exactly so the visual stays faithful.
class TILE:
    VILLAGE = "A"
    IRON_MINE = "I"
    COAL_MINE = "C"
    SULPHUR_MINE = "S"
    FOREST = ";"
    FIELD = ","
    BARRENS = "."
    ROAD = "#"
    HOUSE = "H"
    CAVE = "V"
    TOWN = "O"
    CITY = "Y"
    OUTPOST = "P"
    SHIP = "W"
    BOREHOLE = "B"
    BATTLEFIELD = "F"
    SWAMP = "M"
    CACHE = "U"
    EXECUTIONER = "X"


TILE_PROBS = {
    TILE.FOREST: 0.15,
    TILE.FIELD: 0.35,
    TILE.BARRENS: 0.50,
}
TERRAIN = (TILE.FOREST, TILE.FIELD, TILE.BARRENS)
STICKINESS = 0.5
LIGHT_RADIUS = 2

BASE_WATER = 10
BASE_HEALTH = 10
MOVES_PER_FOOD = 2
MOVES_PER_WATER = 1
FIGHT_CHANCE = 0.20
FIGHT_DELAY = 3
BASE_HIT_CHANCE = 0.8
MEAT_HEAL = 8
MEDS_HEAL = 20


@dataclass
class Landmark:
    glyph: str
    num: int
    min_radius: int
    max_radius: int
    scene: str
    label: str


LANDMARKS: dict[str, Landmark] = {
    TILE.OUTPOST:      Landmark(TILE.OUTPOST,      0,  0,  0,            "outpost",     "An Outpost"),
    TILE.IRON_MINE:    Landmark(TILE.IRON_MINE,    1,  5,  5,            "ironmine",    "Iron Mine"),
    TILE.COAL_MINE:    Landmark(TILE.COAL_MINE,    1, 10, 10,            "coalmine",    "Coal Mine"),
    TILE.SULPHUR_MINE: Landmark(TILE.SULPHUR_MINE, 1, 20, 20,            "sulphurmine", "Sulphur Mine"),
    TILE.HOUSE:        Landmark(TILE.HOUSE,       10,  0, int(RADIUS*1.5), "house",       "An Old House"),
    TILE.CAVE:         Landmark(TILE.CAVE,         5,  3, 10,             "cave",        "A Damp Cave"),
    TILE.TOWN:         Landmark(TILE.TOWN,        10, 10, 20,             "town",        "An Abandoned Town"),
    TILE.CITY:         Landmark(TILE.CITY,        20, 20, int(RADIUS*1.5), "city",        "A Ruined City"),
    TILE.SHIP:         Landmark(TILE.SHIP,         1, 28, 28,             "ship",        "A Crashed Starship"),
    TILE.BOREHOLE:     Landmark(TILE.BOREHOLE,    10, 15, int(RADIUS*1.5), "borehole",    "A Borehole"),
    TILE.BATTLEFIELD:  Landmark(TILE.BATTLEFIELD,  5, 18, int(RADIUS*1.5), "battlefield", "A Battlefield"),
    TILE.SWAMP:        Landmark(TILE.SWAMP,        1, 15, int(RADIUS*1.5), "swamp",       "A Murky Swamp"),
}


def _is_terrain(t: str) -> bool:
    return t in TERRAIN


@dataclass
class SetpieceLoot:
    """Landmark loot roll — simplified single-roll version."""
    items: dict[str, tuple[int, int]]  # name → (min, max) per visit
    msg: str


# Pared-down setpiece loot.  The canonical events.js has multi-scene
# dialogues per landmark; we collapse to a single visit that grants items.
SETPIECE_LOOT: dict[str, SetpieceLoot] = {
    "house": SetpieceLoot(
        {"wood": (2, 5), "cloth": (1, 3)},
        "an old house, long abandoned. a few useful scraps remain.",
    ),
    "cave": SetpieceLoot(
        {"fur": (1, 4), "meat": (1, 3), "scales": (0, 2)},
        "a damp cave. creatures scatter from the torchlight.",
    ),
    "town": SetpieceLoot(
        {"wood": (3, 8), "cloth": (2, 5), "leather": (0, 3), "medicine": (0, 1)},
        "an abandoned town. picked over, but not clean.",
    ),
    "city": SetpieceLoot(
        {"leather": (2, 6), "iron": (1, 4), "coal": (0, 3), "medicine": (0, 2)},
        "a ruined city. much lost, some remains.",
    ),
    "borehole": SetpieceLoot(
        {"coal": (3, 7), "iron": (1, 3), "sulphur": (0, 2)},
        "a deep borehole, edges blackened. useful things at the bottom.",
    ),
    "battlefield": SetpieceLoot(
        {"bullets": (5, 15), "steel": (1, 3), "grenade": (0, 2)},
        "a battlefield. the detritus of war lies cold.",
    ),
    "swamp": SetpieceLoot(
        {"cured meat": (0, 2), "medicine": (0, 2), "energy cell": (0, 1)},
        "the swamp yields strange things to the patient.",
    ),
    "outpost": SetpieceLoot(
        {"cured meat": (3, 5)},
        "the outpost welcomes the weary. water replenished.",
    ),
    "ironmine": SetpieceLoot(
        {"iron": (5, 10)},
        "the iron mine is cleared. villagers can work it now.",
    ),
    "coalmine": SetpieceLoot(
        {"coal": (5, 10)},
        "the coal mine is cleared. villagers can work it now.",
    ),
    "sulphurmine": SetpieceLoot(
        {"sulphur": (5, 10)},
        "the sulphur mine is cleared. villagers can work it now.",
    ),
}


# Encounter table — loot per kill, per distance band.
@dataclass
class Enemy:
    name: str
    health: int
    damage: int
    hit_chance: float = 0.8
    loot: dict[str, tuple[int, int]] = field(default_factory=dict)


ENEMY_TABLE: list[tuple[int, list[Enemy]]] = [
    # (min_distance, [enemies])
    (0, [
        Enemy("a snarling beast", 5, 1, 0.8, {"fur": (1, 3), "meat": (1, 2)}),
        Enemy("a wild dog", 6, 1, 0.8, {"fur": (1, 2), "teeth": (0, 1)}),
    ]),
    (8, [
        Enemy("a feral gaunt", 10, 2, 0.8, {"fur": (2, 4), "scales": (0, 2)}),
        Enemy("a scaled hulk", 14, 3, 0.7, {"scales": (2, 5), "meat": (1, 3)}),
        Enemy("a lumbering monster", 16, 3, 0.8, {"meat": (2, 4), "teeth": (1, 3)}),
    ]),
    (18, [
        Enemy("an armored beast", 24, 4, 0.7, {"scales": (3, 6), "teeth": (2, 4)}),
        Enemy("a twisted huntsman", 30, 5, 0.8, {"leather": (1, 3), "teeth": (2, 5)}),
        Enemy("an armored devil", 36, 6, 0.7, {"scales": (4, 8), "teeth": (3, 6)}),
    ]),
    (26, [
        Enemy("a terrible beast", 50, 8, 0.8, {"teeth": (5, 10), "scales": (5, 10)}),
    ]),
]


@dataclass
class Combat:
    """Ephemeral combat session state."""
    enemy: Enemy
    enemy_hp: int
    ended: bool = False


@dataclass
class WorldState:
    """Live expedition state — wiped on death, committed on goHome()."""
    map: list[list[str]]
    mask: list[list[bool]]
    cur_pos: list[int]  # [x, y]
    water: int
    health: int
    max_water: int
    max_health: int
    food_move: int = 0
    water_move: int = 0
    fight_move: int = 0
    starvation: bool = False
    thirst: bool = False
    dead: bool = False
    used_outposts: set = field(default_factory=set)
    visited_setpieces: set = field(default_factory=set)
    # current loot roll waiting for player pickup
    pending_loot: Optional[SetpieceLoot] = None
    # current combat
    combat: Optional[Combat] = None


class World:
    def __init__(self, engine: "Engine") -> None:
        self.e = engine
        self.state: Optional[WorldState] = None
        self.seen_all = False
        # Persistent world map (stored in engine.state)

    # ---- map generation ------------------------------------------------

    def _choose_tile(self, x: int, y: int, m: list[list[Optional[str]]]) -> str:
        rng = self.e.rng
        adj = [
            m[x][y - 1] if y > 0 else None,
            m[x][y + 1] if y < SIZE - 1 else None,
            m[x + 1][y] if x < SIZE - 1 else None,
            m[x - 1][y] if x > 0 else None,
        ]
        chances: dict[str, float] = {}
        non_sticky = 1.0
        for a in adj:
            if a == TILE.VILLAGE:
                return TILE.FOREST
            if isinstance(a, str):
                chances[a] = chances.get(a, 0.0) + STICKINESS
                non_sticky -= STICKINESS
        for t in TERRAIN:
            chances[t] = chances.get(t, 0.0) + TILE_PROBS[t] * non_sticky
        # pick terrain weighted
        items = sorted(
            [(v, k) for k, v in chances.items() if _is_terrain(k)],
            key=lambda p: -p[0],
        )
        r = rng.random()
        c = 0.0
        for v, k in items:
            c += v
            if r < c:
                return k
        return TILE.BARRENS

    def _place_landmark(self, lm: Landmark, m: list[list[str]]) -> tuple[int, int]:
        rng = self.e.rng
        x = y = RADIUS
        for _ in range(10000):
            if _is_terrain(m[x][y]):
                break
            r = rng.randrange(lm.min_radius, max(lm.max_radius, lm.min_radius + 1))
            xd = rng.randrange(0, r + 1)
            yd = r - xd
            if rng.random() < 0.5:
                xd = -xd
            if rng.random() < 0.5:
                yd = -yd
            x = max(0, min(SIZE - 1, RADIUS + xd))
            y = max(0, min(SIZE - 1, RADIUS + yd))
        m[x][y] = lm.glyph
        return x, y

    def generate_map(self) -> list[list[str]]:
        m: list[list[str]] = [[""] * SIZE for _ in range(SIZE)]
        m[RADIUS][RADIUS] = TILE.VILLAGE
        # spiral out, matching the JS expanding-ring fill order
        for r in range(1, RADIUS + 1):
            for t in range(r * 8):
                if t < 2 * r:
                    x = RADIUS - r + t
                    y = RADIUS - r
                elif t < 4 * r:
                    x = RADIUS + r
                    y = RADIUS - 3 * r + t
                elif t < 6 * r:
                    x = RADIUS + 5 * r - t
                    y = RADIUS + r
                else:
                    x = RADIUS - r
                    y = RADIUS + 7 * r - t
                m[x][y] = self._choose_tile(x, y, m)
        for lm in LANDMARKS.values():
            for _ in range(lm.num):
                self._place_landmark(lm, m)
        return m

    def _new_mask(self) -> list[list[bool]]:
        mask = [[False] * SIZE for _ in range(SIZE)]
        self._light_map(RADIUS, RADIUS, mask)
        return mask

    def _light_map(self, x: int, y: int, mask: list[list[bool]]) -> None:
        r = LIGHT_RADIUS
        mask[x][y] = True
        for i in range(-r, r + 1):
            j_range = r - abs(i)
            for j in range(-r + abs(i), j_range + 1):
                if 0 <= x + i < SIZE and 0 <= y + j < SIZE:
                    mask[x + i][y + j] = True

    # ---- persistence ---------------------------------------------------

    def init(self) -> None:
        e = self.e
        if e.get("features", "location", "world") is None:
            e.set("features", "location", "world", value=True)
            e.set("game", "world", value={
                "map": self.generate_map(),
                "mask": self._new_mask(),
            })

    def max_water(self) -> int:
        s = self.e.stores_get
        if s("water tank") > 0:
            return BASE_WATER + 50
        if s("cask") > 0:
            return BASE_WATER + 20
        if s("waterskin") > 0:
            return BASE_WATER + 10
        return BASE_WATER

    def max_health(self) -> int:
        s = self.e.stores_get
        if s("s armour") > 0:
            return BASE_HEALTH + 35
        if s("i armour") > 0:
            return BASE_HEALTH + 15
        if s("l armour") > 0:
            return BASE_HEALTH + 5
        return BASE_HEALTH

    # ---- embark / return ----------------------------------------------

    def on_arrival(self, outfit: dict[str, int]) -> None:
        """Begin an expedition with a copy of the persistent map."""
        e = self.e
        src = e.get("game", "world", default={"map": [], "mask": []})
        # deepcopy needed since we mutate mask as we uncover
        mp = [list(row) for row in src["map"]]
        mk = [list(row) for row in src["mask"]]
        self.state = WorldState(
            map=mp,
            mask=mk,
            cur_pos=[RADIUS, RADIUS],
            water=self.max_water(),
            health=self.max_health(),
            max_water=self.max_water(),
            max_health=self.max_health(),
        )
        self.outfit = dict(outfit)
        e.notify("world", "a barren world")
        e.emit("world_arrival")

    def die(self) -> None:
        assert self.state is not None
        self.state.dead = True
        self.e.notify("world", "the world fades")
        self.state = None
        self.outfit = {}
        self.e.emit("sound", "death")
        self.e.emit("world_death")

    def go_home(self) -> None:
        """Commit expedition changes: reveal mask, unlock mines, stash loot."""
        e = self.e
        if self.state is None:
            return
        # commit mask and map to persistent world
        world = e.get("game", "world", default={})
        world["map"] = [list(row) for row in self.state.map]
        world["mask"] = [list(row) for row in self.state.mask]
        e.set("game", "world", value=world)
        # unlock mines if we visited them
        for sp, name in (("sulphurmine", "sulphur mine"),
                         ("ironmine", "iron mine"),
                         ("coalmine", "coal mine")):
            if sp in self.state.visited_setpieces:
                b = e.state.setdefault("game", {}).setdefault("buildings", {})
                if (b.get(name, 0) or 0) == 0:
                    b[name] = 1
                    e.emit("buildings_changed", name, 1)
                    e.notify(None, f"{name} found and cleared")
        if "ship" in self.state.visited_setpieces and not e.get("features", "location", "spaceShip"):
            e.set("features", "location", "spaceShip", value=True)
            e.notify(None, "a crashed starship. a way off this rock, maybe.")
            e.emit("ship_found")
        # return outfit to stores (cured meat / bullets stay on person in JS;
        # we send everything back to stores for simplicity and restock on next embark).
        for k, v in list(self.outfit.items()):
            if v > 0:
                e.stores_add(k, v)
        self.outfit = {}
        self.state = None
        e.emit("world_return")

    # ---- movement ------------------------------------------------------

    def move(self, dx: int, dy: int) -> None:
        """Move one tile if possible; updates mask, consumes supplies, rolls fight."""
        if self.state is None or self.state.dead:
            return
        x, y = self.state.cur_pos
        nx, ny = x + dx, y + dy
        if not (0 <= nx < SIZE and 0 <= ny < SIZE):
            return
        old_tile = self.state.map[x][y]
        self.state.cur_pos = [nx, ny]
        new_tile = self.state.map[nx][ny]
        self._narrate_move(old_tile, new_tile)
        self._light_map(nx, ny, self.state.mask)
        # random footstep sfx
        self.e.emit("sound", f"footstep{self.e.rng.randint(1, 5)}")
        # landmark / combat interaction
        if new_tile == TILE.VILLAGE:
            self.go_home()
            return
        if new_tile in LANDMARKS:
            lm = LANDMARKS[new_tile]
            # outposts reusable-once
            if new_tile == TILE.OUTPOST:
                key = (nx, ny)
                if key not in self.state.used_outposts:
                    self.state.used_outposts.add(key)
                    self.state.water = self.state.max_water
                    self.e.notify("world", "water replenished")
                return
            if lm.scene in SETPIECE_LOOT and lm.scene not in self.state.visited_setpieces:
                self.state.visited_setpieces.add(lm.scene)
                self.state.pending_loot = SETPIECE_LOOT[lm.scene]
                self.e.notify("world", SETPIECE_LOOT[lm.scene].msg)
                self._apply_pending_loot()
                # on ship-find, mark for goHome commit
                if lm.scene == "ship":
                    self.e.notify("world", "a crashed starship. the ship's hull is cracked open.")
            return
        if self._use_supplies():
            self._check_fight()

    def _apply_pending_loot(self) -> None:
        assert self.state is not None
        loot = self.state.pending_loot
        if loot is None:
            return
        rng = self.e.rng
        parts = []
        for name, (mn, mx) in loot.items.items():
            n = rng.randint(mn, mx)
            if n > 0:
                self.outfit[name] = (self.outfit.get(name) or 0) + n
                parts.append(f"{n} {name}")
        if parts:
            self.e.notify("world", "found: " + ", ".join(parts))
        self.state.pending_loot = None

    def _narrate_move(self, old: str, new: str) -> None:
        msg = None
        if old == TILE.FOREST and new == TILE.FIELD:
            msg = "the trees yield to dry grass. the yellowed brush rustles in the wind."
        elif old == TILE.FOREST and new == TILE.BARRENS:
            msg = "the trees are gone. parched earth and blowing dust are poor replacements."
        elif old == TILE.FIELD and new == TILE.FOREST:
            msg = "trees loom on the horizon."
        elif old == TILE.FIELD and new == TILE.BARRENS:
            msg = "the grasses thin. soon, only dust remains."
        elif old == TILE.BARRENS and new == TILE.FIELD:
            msg = "the barrens break at a sea of dying grass, swaying in the arid breeze."
        elif old == TILE.BARRENS and new == TILE.FOREST:
            msg = "a wall of gnarled trees rises from the dust."
        if msg:
            self.e.notify("world", msg)

    def _use_supplies(self) -> bool:
        """Consume food/water per move. Returns False if dead."""
        assert self.state is not None
        s = self.state
        s.food_move += 1
        s.water_move += 1
        if s.food_move >= MOVES_PER_FOOD:
            s.food_move = 0
            meat = self.outfit.get("cured meat", 0) - 1
            if meat == 0:
                self.e.notify("world", "the meat has run out")
            elif meat < 0:
                meat = 0
                if not s.starvation:
                    self.e.notify("world", "starvation sets in")
                    s.starvation = True
                else:
                    self.die()
                    return False
            else:
                s.starvation = False
                s.health = min(s.max_health, s.health + MEAT_HEAL)
            self.outfit["cured meat"] = meat
        if s.water_move >= MOVES_PER_WATER:
            s.water_move = 0
            s.water -= 1
            if s.water == 0:
                self.e.notify("world", "there is no more water")
            elif s.water < 0:
                s.water = 0
                if not s.thirst:
                    self.e.notify("world", "the thirst becomes unbearable")
                    s.thirst = True
                else:
                    self.die()
                    return False
            else:
                s.thirst = False
        return True

    def _check_fight(self) -> None:
        assert self.state is not None
        s = self.state
        s.fight_move += 1
        if s.fight_move <= FIGHT_DELAY:
            return
        if self.e.rng.random() < FIGHT_CHANCE:
            s.fight_move = 0
            self._start_fight()

    def _start_fight(self) -> None:
        assert self.state is not None
        dist = abs(self.state.cur_pos[0] - RADIUS) + abs(self.state.cur_pos[1] - RADIUS)
        pool: list[Enemy] = []
        for threshold, enemies in ENEMY_TABLE:
            if dist >= threshold:
                pool = enemies
        enemy = self.e.rng.choice(pool)
        # clone so mutations don't persist
        fresh = Enemy(enemy.name, enemy.health, enemy.damage, enemy.hit_chance, dict(enemy.loot))
        self.state.combat = Combat(enemy=fresh, enemy_hp=fresh.health)
        self.e.notify("world", f"{fresh.name} blocks the path")
        self.e.emit("combat_begin", fresh)
        self.e.emit("sound", "encounter1")

    # ---- combat public API --------------------------------------------

    def combat_attack(self, weapon: str = "fists") -> None:
        """Player swings. Enemy counter-attacks. End-conditions handled."""
        if self.state is None or self.state.combat is None or self.state.combat.ended:
            return
        from .path import WEAPONS
        w = WEAPONS.get(weapon, WEAPONS["fists"])
        combat = self.state.combat
        # player swings
        if self.e.rng.random() < BASE_HIT_CHANCE:
            dmg = w.damage if isinstance(w.damage, int) else 0
            combat.enemy_hp -= dmg
            self.e.notify("world", f"{w.verb} — {dmg} damage")
        else:
            self.e.notify("world", "miss")
        if combat.enemy_hp <= 0:
            self._win_fight()
            return
        # enemy counter
        if self.e.rng.random() < combat.enemy.hit_chance:
            self.state.health -= combat.enemy.damage
            self.e.notify("world", f"hit for {combat.enemy.damage}")
            if self.state.health <= 0:
                self.die()
                return
        else:
            self.e.notify("world", f"{combat.enemy.name} misses")

    def combat_flee(self) -> None:
        if self.state is None or self.state.combat is None:
            return
        self.state.combat.ended = True
        self.state.combat = None
        self.e.notify("world", "fled the fight")
        self.e.emit("combat_end", False)

    def combat_eat_meat(self) -> None:
        if self.state is None:
            return
        if (self.outfit.get("cured meat") or 0) <= 0:
            self.e.notify("world", "no meat to eat")
            return
        self.outfit["cured meat"] -= 1
        heal = MEAT_HEAL
        self.state.health = min(self.state.max_health, self.state.health + heal)
        self.e.notify("world", f"eat meat — heal {heal}")
        self.e.emit("sound", "eatMeat")

    def _win_fight(self) -> None:
        assert self.state is not None and self.state.combat is not None
        enemy = self.state.combat.enemy
        self.e.notify("world", f"the {enemy.name} is dead")
        parts = []
        for name, (mn, mx) in enemy.loot.items():
            n = self.e.rng.randint(mn, mx)
            if n > 0:
                self.outfit[name] = (self.outfit.get(name) or 0) + n
                parts.append(f"{n} {name}")
        if parts:
            self.e.notify("world", "loot: " + ", ".join(parts))
        self.state.combat.ended = True
        self.state.combat = None
        self.e.emit("combat_end", True)

    # ---- queries -------------------------------------------------------

    def render_visible(self) -> list[str]:
        """Return the map as a list of strings, masked by fog-of-war.

        `@` marks the wanderer's position.  Unrevealed tiles are spaces.
        """
        if self.state is None:
            return []
        rows: list[str] = []
        cx, cy = self.state.cur_pos
        for y in range(SIZE):
            row_chars: list[str] = []
            for x in range(SIZE):
                if x == cx and y == cy:
                    row_chars.append("@")
                elif self.state.mask[x][y]:
                    row_chars.append(self.state.map[x][y])
                else:
                    row_chars.append(" ")
            rows.append("".join(row_chars))
        return rows

    def get_pos(self) -> tuple[int, int]:
        if self.state is None:
            return VILLAGE_POS
        return tuple(self.state.cur_pos)  # type: ignore

    def status_line(self) -> str:
        if self.state is None:
            return ""
        return (f"hp {self.state.health}/{self.state.max_health}"
                f"  water {self.state.water}/{self.state.max_water}"
                f"  meat {self.outfit.get('cured meat', 0)}")
