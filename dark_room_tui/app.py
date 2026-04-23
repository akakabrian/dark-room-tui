"""Textual app — the A Dark Room TUI shell.

Layout (aesthetic decision in DECISIONS.md):

    ┌ Title / Tabs ────────────────────────────────────────┐
    ├────────────────────────────┬─────────────────────────┤
    │  Active location panel     │  Stores (right sidebar) │
    ├────────────────────────────┴─────────────────────────┤
    │  Event log (RichLog)                                 │
    └──────────────────────────────────────────────────────┘

Location panel cycles: Room / Outside / Path / World / Ship as the game
progresses.  Key bindings are single-letter, mirroring the web game's
button-heavy UI but keyboard-first.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog, Static

from .engine import Engine, Notification
from .outside import Outside, INCOME as OUTSIDE_INCOME
from .path import Path, OUTFITTABLE, WEAPONS
from .room import Room, CRAFTABLES, TRADE_GOODS, FIRE_NAMES, TEMP_NAMES
from .ship import Ship
from .sound import SoundEngine
from .world import RADIUS, SIZE, TILE, World


LOCATIONS = ["room", "outside", "path", "world", "ship"]

LOCATION_LABELS = {
    "room": "A Dark Room",
    "outside": "A Silent Forest",
    "path": "A Dusty Path",
    "world": "The World",
    "ship": "A Starship",
}

# Colors per tile class for the world view.
TILE_STYLES = {
    TILE.VILLAGE:      "bold #ffbb44",
    TILE.FOREST:       "#56a860",
    TILE.FIELD:        "#cbc05c",
    TILE.BARRENS:      "#8b6c42",
    TILE.ROAD:         "#666666",
    TILE.HOUSE:        "#aaaaaa",
    TILE.CAVE:         "#7755aa",
    TILE.TOWN:         "#cccccc",
    TILE.CITY:         "#ffffff",
    TILE.OUTPOST:      "bold cyan",
    TILE.IRON_MINE:    "#c1744f",
    TILE.COAL_MINE:    "#8a8a8a",
    TILE.SULPHUR_MINE: "#e8d04a",
    TILE.SHIP:         "bold magenta",
    TILE.BOREHOLE:     "#553333",
    TILE.BATTLEFIELD:  "bold red",
    TILE.SWAMP:        "#556644",
    TILE.CACHE:        "bold green",
    "@":               "bold white on #6688aa",
}

MODULE_STYLES = {
    "room":    "#ffbb44",
    "outside": "#56a860",
    "path":    "#aaaaaa",
    "world":   "#88aaff",
    "ship":    "magenta",
    None:      "white",
}


def _style_for(module: str | None) -> str:
    return MODULE_STYLES.get(module, "white")


class StoresPanel(Static):
    """Right sidebar — stores + income rates."""

    def build_text(self, engine: Engine, outside: Outside) -> Text:
        """Assemble the panel's Text (no Textual update — benchmarkable)."""
        stores = engine.state.get("stores") or {}
        income = engine.state.get("income") or {}
        income_by_store: dict[str, float] = {}
        for _src, payload in income.items():
            delay = max(1e-9, payload.get("delay", 10))
            for k, v in (payload.get("stores") or {}).items():
                income_by_store[k] = income_by_store.get(k, 0.0) + v / delay

        t = Text()
        t.append("stores\n", style="bold underline")
        # Sort stores by a rough importance order: wood first, then alpha.
        order = ["wood", "fur", "meat", "cured meat", "leather", "bait",
                 "scales", "teeth", "cloth", "iron", "coal", "sulphur",
                 "steel", "bullets", "medicine", "energy cell",
                 "grenade", "bolas", "charm", "compass", "alien alloy"]
        shown: set[str] = set()
        for k in order:
            v = stores.get(k, 0)
            if v and int(v) > 0:
                self._line(t, k, int(v), income_by_store.get(k, 0.0))
                shown.add(k)
        for k, v in sorted(stores.items()):
            if k in shown or not v or int(v) <= 0:
                continue
            self._line(t, k, int(v), income_by_store.get(k, 0.0))
        # population / workers
        pop = engine.get("game", "population") or 0
        cap = outside.max_population()
        if pop or cap:
            t.append("\n")
            t.append("villagers\n", style="bold underline")
            t.append(f"  pop    {pop}/{cap}\n")
            free = outside.num_gatherers()
            t.append(f"  free   {free}\n", style="dim")
            workers = engine.get("game", "workers") or {}
            for job in sorted(workers):
                n = workers[job]
                if n:
                    t.append(f"  {job:<10} {int(n)}\n")
        return t

    def refresh_panel(self, engine: Engine, outside: Outside) -> None:
        self.update(self.build_text(engine, outside))

    @staticmethod
    def _line(t: Text, name: str, n: int, rate: float) -> None:
        t.append(f"  {name:<13} ", style="white")
        t.append(f"{n:>6}", style="bold")
        if rate:
            sign = "+" if rate > 0 else ""
            t.append(f"  {sign}{rate:.1f}/s", style="green" if rate > 0 else "red")
        t.append("\n")


class LocationPanel(Static):
    """Main panel — renders the active location view."""

    def refresh_panel(self, app_state: "DarkRoomApp") -> None:
        mod = app_state.active_location
        renderer = {
            "room":    self._render_room,
            "outside": self._render_outside,
            "path":    self._render_path,
            "world":   self._render_world,
            "ship":    self._render_ship,
        }[mod]
        self.update(renderer(app_state))

    # --- per-location renderers -----------------------------------------

    def _render_room(self, s: "DarkRoomApp") -> Text:
        e = s.engine
        r = s.room
        t = Text()
        # Fire color warms with level (dim gray → bright gold)
        fire_level = e.get("game", "fire", "value") or 0
        fire_colors = ["#555555", "#7a5a22", "#b8812a", "#dfa43d", "#ffbb44"]
        t.append(r.title() + "\n\n", style="bold " + fire_colors[fire_level])
        # Fire as a glyph row
        fire_glyph = "·" if fire_level == 0 else "▴" * max(1, fire_level)
        t.append(f"  fire: {r.fire_name():<12} {fire_glyph}\n",
                 style=fire_colors[fire_level])
        t.append(f"  room: {r.temp_name()}\n\n")

        actions = []
        if e.get("game", "fire", "value") == 0:
            actions.append(("L", "light fire"))
        else:
            actions.append(("S", "stoke fire"))

        builder = e.get("game", "builder", "level") or -1
        if builder >= 4:
            actions.append(("T", "trap"))
            actions.append(("C", "cart"))
            actions.append(("H", "hut"))
            actions.append(("O", "lodge"))
            actions.append(("P", "trading post"))

        t.append("  actions:\n", style="bold")
        for key, label in actions:
            t.append(f"    [{key}] {label}\n")

        # Craft & buy (when buildings exist)
        if builder >= 4:
            avail = r.available_buildings()
            # present remainder of buildings/items (not already in hotkey row)
            hotkey_items = {"trap", "cart", "hut", "lodge", "trading post"}
            extra = [a for a in avail if a not in hotkey_items]
            if extra:
                t.append("\n  craft/build (press B then digit):\n", style="bold")
                for i, name in enumerate(extra[:9]):
                    t.append(f"    [{i+1}] {name}\n")
                # stash mapping so key handlers can find it
                s.craft_menu = extra[:9]
            else:
                s.craft_menu = []
            trade = r.available_trade()
            if trade:
                t.append("\n  buy (press Y then digit):\n", style="bold")
                for i, name in enumerate(trade[:9]):
                    t.append(f"    [{i+1}] {name}\n")
                s.buy_menu = trade[:9]
            else:
                s.buy_menu = []
        return t

    def _render_outside(self, s: "DarkRoomApp") -> Text:
        e = s.engine
        o = s.outside
        t = Text()
        t.append(o.title() + "\n\n", style="bold " + MODULE_STYLES["outside"])
        pop = e.get("game", "population") or 0
        t.append(f"  pop: {pop}/{o.max_population()}\n\n")

        cg_left = max(0.0, 60.0 - (e.time - o.last_gather_time))
        ct_left = max(0.0, 90.0 - (e.time - o.last_traps_time))
        t.append("  actions:\n", style="bold")
        t.append(f"    [G] gather wood  {self._bar(cg_left, 60.0)}\n")
        traps = (e.get("game", "buildings") or {}).get("trap", 0) or 0
        if traps > 0:
            t.append(f"    [K] check traps {self._bar(ct_left, 90.0)}\n")

        workers = e.get("game", "workers") or {}
        if workers:
            t.append("\n  workers:  (press W+digit to +1, Q+digit to -1)\n", style="bold")
            # enumerate stable order
            jobs = sorted(workers)
            s.worker_menu = jobs[:9]
            for i, j in enumerate(jobs[:9]):
                t.append(f"    [{i+1}] {j:<12} {int(workers[j])}\n")
        else:
            s.worker_menu = []
        free = o.num_gatherers()
        t.append(f"\n  free gatherers: {free}\n", style="dim")
        return t

    def _render_path(self, s: "DarkRoomApp") -> Text:
        e = s.engine
        p = s.path
        t = Text()
        t.append("A Dusty Path\n\n", style="bold " + MODULE_STYLES["path"])
        t.append(f"  bag:  {int(p.capacity() - p.free_space())}/{p.capacity()}\n\n")
        t.append("  outfit:  (press + / - then digit)\n", style="bold")
        items = p.outfittable()
        s.outfit_menu = items[:9]
        for i, k in enumerate(items[:9]):
            n = p.outfit.get(k, 0)
            in_stores = int(e.stores_get(k))
            t.append(f"    [{i+1}] {k:<14} {n:>3}   (have {in_stores})\n")
        if not items:
            t.append("    (nothing to take — gather supplies first)\n", style="dim")
        ready = (p.outfit.get("cured meat", 0) or 0) > 0
        t.append("\n  actions:\n", style="bold")
        t.append(f"    [E] embark  {'(need cured meat)' if not ready else ''}\n",
                 style="white" if ready else "dim")
        return t

    def _render_world(self, s: "DarkRoomApp") -> Text:
        w = s.world
        t = Text()
        t.append("the wasteland\n\n", style="bold " + MODULE_STYLES["world"])
        if w.state is None:
            t.append("  not out there.  embark from the path.\n", style="dim")
            return t
        # pick a 27x15 view centred on the player
        cx, cy = w.state.cur_pos
        vw, vh = 27, 15
        x0 = max(0, min(SIZE - vw, cx - vw // 2))
        y0 = max(0, min(SIZE - vh, cy - vh // 2))
        for y in range(y0, y0 + vh):
            for x in range(x0, x0 + vw):
                if x == cx and y == cy:
                    ch = "@"; style = TILE_STYLES["@"]
                elif w.state.mask[x][y]:
                    ch = w.state.map[x][y] or " "
                    style = TILE_STYLES.get(ch, "white")
                else:
                    ch = " "; style = "black on black"
                t.append(ch + " ", style=style)
            t.append("\n")
        t.append("\n")
        t.append(f"  {w.status_line()}\n")
        t.append("  [↑/↓/←/→ or w/a/s/d] move   [R] return to village\n", style="dim")
        if w.state.combat:
            c = w.state.combat
            t.append(f"\n  COMBAT: {c.enemy.name} (hp {c.enemy_hp}/{c.enemy.health})\n",
                     style="bold red")
            t.append("  [F] fight   [X] flee   [M] eat meat\n", style="dim")
        return t

    def _render_ship(self, s: "DarkRoomApp") -> Text:
        sh = s.ship
        t = Text()
        t.append("An Old Starship\n\n", style="bold " + MODULE_STYLES["ship"])
        t.append(f"  hull:     {sh.hull()}\n")
        t.append(f"  engine:   {sh.thrusters()}\n\n")
        t.append("  actions:\n", style="bold")
        t.append("    [U] reinforce hull    (costs 1 alien alloy)\n")
        t.append("    [I] upgrade engine    (costs 1 alien alloy)\n")
        if sh.can_lift_off():
            t.append("    [Z] lift off\n")
        else:
            t.append("    [Z] lift off          (hull must be > 0)\n", style="dim")
        if sh.lifted_off:
            t.append("\n")
            t.append("  ** victory **\n", style="bold magenta")
            t.append("  the ship lifts off through the haze.\n")
            t.append("  above the clouds, the stars.\n\n")
            t.append(f"  played {s.engine.time:.0f}s of game time\n", style="dim")
        return t

    # --- helpers --------------------------------------------------------

    @staticmethod
    def _cd(seconds: float) -> str:
        if seconds <= 0:
            return "ready"
        return f"{seconds:4.0f}s"

    @staticmethod
    def _bar(remaining: float, total: float, width: int = 10) -> str:
        """Render a cooldown bar: [####······]  12s  (or 'ready')."""
        if remaining <= 0:
            return "[" + "#" * width + "]  ready"
        frac = 1.0 - remaining / total
        filled = int(width * frac)
        body = "#" * filled + "·" * (width - filled)
        return f"[{body}] {remaining:4.0f}s"


class DarkRoomApp(App):
    CSS_PATH = "tui.tcss"

    BINDINGS = [
        Binding("1", "goto('room')",    "Room",     show=True),
        Binding("2", "goto('outside')", "Outside",  show=True),
        Binding("3", "goto('path')",    "Path",     show=True),
        Binding("4", "goto('world')",   "World",    show=True),
        Binding("5", "goto('ship')",    "Ship",     show=True),
        Binding("q", "quit",            "Quit",     show=True),
        # Room
        Binding("l", "light",  "Light fire"),
        Binding("s", "stoke",  "Stoke"),
        Binding("t", "build('trap')"),
        Binding("c", "build('cart')"),
        Binding("h", "build('hut')"),
        Binding("o", "build('lodge')"),
        Binding("p", "build('trading post')"),
        # craft/buy sub-modes
        Binding("b", "mode('craft')", "Craft prefix"),
        Binding("y", "mode('buy')",   "Buy prefix"),
        # Outside
        Binding("g", "gather",    "Gather"),
        Binding("k", "check_traps", "Traps"),
        # path outfit edit prefixes
        Binding("plus",  "mode('out+')"),
        Binding("equals_sign", "mode('out+')"),  # defensive (older Textual)
        Binding("minus", "mode('out-')"),
        Binding("e", "embark"),
        # world
        Binding("up",    "move(0,-1)", show=False, priority=True),
        Binding("down",  "move(0,1)",  show=False, priority=True),
        Binding("left",  "move(-1,0)", show=False, priority=True),
        Binding("right", "move(1,0)",  show=False, priority=True),
        Binding("w", "move(0,-1)"),
        Binding("a", "move(-1,0)"),
        Binding("d", "move(1,0)"),
        # 's' is stoke; in world view we map 'x' for south so stoke stays free
        Binding("x", "combat_flee"),
        Binding("r", "go_home"),
        Binding("f", "combat_attack"),
        Binding("m", "combat_eat"),
        # ship
        Binding("u", "reinforce"),
        Binding("i", "upgrade_engine"),
        Binding("z", "lift_off"),
        # worker prefix
        Binding("question_mark", "help"),
    ]

    active_location: reactive[str] = reactive("room")
    pending_mode: reactive[str] = reactive("")  # '' | 'craft' | 'buy' | 'out+' | 'out-'

    def __init__(self, seed: int | None = None, mute: bool = False) -> None:
        super().__init__()
        self.engine = Engine(seed=seed)
        self.room = Room(self.engine)
        self.outside = Outside(self.engine)
        self.world = World(self.engine)
        self.path = Path(self.engine, self.world)
        self.ship = Ship(self.engine)
        self.sound = SoundEngine(enabled=not mute)

        # UI-side menus filled by the location renderers
        self.craft_menu: list[str] = []
        self.buy_menu: list[str] = []
        self.worker_menu: list[str] = []
        self.outfit_menu: list[str] = []

        self._event_log: RichLog | None = None
        self._stores: StoresPanel | None = None
        self._location: LocationPanel | None = None
        self._title: Static | None = None

    # --- textual lifecycle ----------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        self._title = Static("A Dark Room", id="title")
        yield self._title
        with Horizontal(id="main"):
            self._location = LocationPanel(id="location")
            yield self._location
            self._stores = StoresPanel("", id="stores")
            yield self._stores
        self._event_log = RichLog(id="log", wrap=True, markup=False,
                                  highlight=False, max_lines=500,
                                  auto_scroll=True)
        yield self._event_log
        yield Footer()

    def on_mount(self) -> None:
        self.room.init()
        # engine event subscriptions — pipe notifications to RichLog
        self.engine.on("notify", self._handle_notify)
        self.engine.on("unlock_forest", self._on_unlock_forest)
        self.engine.on("lodge_built", lambda: None)
        self.engine.on("builder_helping", self._on_builder_helping)
        self.engine.on("ship_found", self._on_ship_found)
        self.engine.on("world_return", self._on_world_return)
        self.engine.on("world_arrival", self._on_world_arrival)
        self.engine.on("combat_end", self._on_combat_end)
        self.engine.on("sound", lambda tag: self.sound.play(tag))
        # start the timers
        self.set_interval(0.1, self._tick)
        self.set_interval(0.5, self._refresh_ui)
        self._refresh_ui()

    # --- timers ---------------------------------------------------------

    def _tick(self) -> None:
        self.engine.advance(0.1)
        self.engine.collect_income(0.1)

    def _refresh_ui(self) -> None:
        if self._location:
            self._location.refresh_panel(self)
        if self._stores:
            self._stores.refresh_panel(self.engine, self.outside)
        if self._title:
            mod = self.active_location
            label = self.room.title() if mod == "room" else LOCATION_LABELS[mod]
            badge = " | ".join(
                f"{'*' if loc == mod else ' '}{i+1} {LOCATION_LABELS[loc]}"
                for i, loc in enumerate(self._visible_locations())
            )
            self._title.update(f"{label}\n{badge}")

    def _visible_locations(self) -> list[str]:
        feats = self.engine.get("features", "location") or {}
        out = ["room"]
        if feats.get("outside"):
            out.append("outside")
        if feats.get("path"):
            out.append("path")
        if feats.get("world") and self.world.state is not None:
            out.append("world")
        if feats.get("spaceShip"):
            out.append("ship")
        return out

    # --- event handlers --------------------------------------------------

    def _handle_notify(self, note: Notification) -> None:
        if self._event_log is None:
            return
        t = Text()
        t.append(f"[{self.engine.time:6.1f}] ", style="dim")
        if note.module:
            t.append(f"{note.module}: ", style=_style_for(note.module))
        t.append(note.text)
        self._event_log.write(t)

    def _on_unlock_forest(self) -> None:
        self.outside.init()
        # also unlock the path as soon as the forest is walkable
        # in the JS the path unlocks after the first embarkation prereq —
        # we mirror that by unlocking after trading post OR after workshop.

    def _on_builder_helping(self) -> None:
        # enables outside actions + unlocks path once the compass is bought
        self.outside.init()

    def _on_ship_found(self) -> None:
        self.ship.init()

    def _on_world_arrival(self) -> None:
        self.active_location = "world"

    def _on_world_return(self) -> None:
        if self.active_location == "world":
            self.active_location = "path"

    def _on_combat_end(self, _won: bool) -> None:
        pass  # renderer picks it up

    # --- actions --------------------------------------------------------

    def action_goto(self, mod: str) -> None:
        if mod in self._visible_locations():
            self.active_location = mod

    def action_light(self) -> None:
        if self.active_location == "room":
            self.room.light_fire()

    def action_stoke(self) -> None:
        if self.active_location == "room":
            self.room.stoke_fire()

    def action_build(self, thing: str) -> None:
        if self.active_location != "room":
            return
        built = self.room.build(thing)
        # first hut / lodge / trading post may auto-unlock path
        if built and thing in ("trading post", "lodge"):
            self.path.init()

    def action_mode(self, mode: str) -> None:
        self.pending_mode = mode

    def action_gather(self) -> None:
        if self.active_location == "outside":
            self.outside.gather_wood()

    def action_check_traps(self) -> None:
        if self.active_location == "outside":
            self.outside.check_traps()

    def action_embark(self) -> None:
        if self.active_location == "path":
            self.path.embark()

    def action_move(self, dx: int, dy: int) -> None:
        if self.active_location != "world":
            return
        self.world.move(dx, dy)

    def action_combat_attack(self) -> None:
        if self.active_location == "world" and self.world.state and self.world.state.combat:
            # pick best available weapon
            w = self._best_weapon()
            self.world.combat_attack(w)

    def action_combat_flee(self) -> None:
        if self.active_location == "world" and self.world.state and self.world.state.combat:
            self.world.combat_flee()

    def action_combat_eat(self) -> None:
        if self.active_location == "world":
            self.world.combat_eat_meat()

    def action_go_home(self) -> None:
        if self.active_location == "world":
            self.world.go_home()

    def action_reinforce(self) -> None:
        if self.active_location == "ship":
            self.ship.reinforce_hull()

    def action_upgrade_engine(self) -> None:
        if self.active_location == "ship":
            self.ship.upgrade_engine()

    def action_lift_off(self) -> None:
        if self.active_location == "ship":
            self.ship.lift_off()

    def action_help(self) -> None:
        self.engine.notify(None, "keys: 1-5 locations, L light, S stoke, G gather, K traps, E embark, arrows move, R return, F fight, X flee")

    # --- digit keys + prefix modes --------------------------------------

    async def on_key(self, event) -> None:
        k = event.key
        if self.pending_mode and k.isdigit() and k != "0":
            idx = int(k) - 1
            mode = self.pending_mode
            self.pending_mode = ""
            if mode == "craft":
                if 0 <= idx < len(self.craft_menu):
                    self.action_build(self.craft_menu[idx])
            elif mode == "buy":
                if 0 <= idx < len(self.buy_menu):
                    self.room.buy(self.buy_menu[idx])
            elif mode == "out+":
                if 0 <= idx < len(self.outfit_menu):
                    self.path.increase(self.outfit_menu[idx])
            elif mode == "out-":
                if 0 <= idx < len(self.outfit_menu):
                    self.path.decrease(self.outfit_menu[idx])
            event.stop()
            return
        # worker +/-: 'w'+digit or 'q'+digit
        if k.isdigit() and k != "0" and self.pending_mode in ("w+", "w-"):
            idx = int(k) - 1
            mode = self.pending_mode
            self.pending_mode = ""
            if 0 <= idx < len(self.worker_menu):
                if mode == "w+":
                    self.outside.increase_worker(self.worker_menu[idx])
                else:
                    self.outside.decrease_worker(self.worker_menu[idx])
            event.stop()

    # --- helpers --------------------------------------------------------

    def _best_weapon(self) -> str:
        """Pick the best melee/ranged the player brought in outfit or has."""
        pref = ["plasma rifle", "laser rifle", "rifle", "steel sword",
                "iron sword", "bayonet", "bone spear", "fists"]
        for name in pref:
            w = WEAPONS[name]
            if name == "fists":
                return name
            have = (self.world.outfit.get(name, 0) if self.world.state else 0) \
                if self.world.state else 0
            if have > 0:
                # also require ammo if costed
                for res, amt in (w.cost or {}).items():
                    if (self.world.outfit.get(res, 0) or 0) < amt:
                        break
                else:
                    return name
        return "fists"


def main() -> None:  # pragma: no cover
    DarkRoomApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
