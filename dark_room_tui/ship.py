"""Ship module — port of vendor/adarkroom/script/ship.js.

Once the crashed starship is found in the world, the Ship tab unlocks.
Player spends alien alloy to reinforce hull & upgrade engine.  Liftoff
ends the game (victory flag + stats).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Engine


BASE_HULL = 0
BASE_THRUSTERS = 1
ALLOY_PER_HULL = 1
ALLOY_PER_THRUSTER = 1


class Ship:
    def __init__(self, engine: "Engine") -> None:
        self.e = engine
        self.lifted_off = False

    def init(self) -> None:
        e = self.e
        if e.get("features", "location", "spaceShip") is None:
            e.set("features", "location", "spaceShip", value=True)
        if e.get("game", "spaceShip", default=None) is None:
            e.set("game", "spaceShip", value={
                "hull": BASE_HULL,
                "thrusters": BASE_THRUSTERS,
                "seenShip": False,
            })
        if not e.get("game", "spaceShip", "seenShip"):
            e.set("game", "spaceShip", "seenShip", value=True)
            e.notify(
                "ship",
                "somewhere above the debris cloud, the wanderer fleet hovers. "
                "been on this rock too long.",
            )

    # ---- queries --------------------------------------------------------

    def hull(self) -> int:
        return self.e.get("game", "spaceShip", "hull") or 0

    def thrusters(self) -> int:
        return self.e.get("game", "spaceShip", "thrusters") or 1

    def can_lift_off(self) -> bool:
        return self.hull() > 0

    # ---- actions --------------------------------------------------------

    def reinforce_hull(self) -> bool:
        e = self.e
        if e.stores_get("alien alloy") < ALLOY_PER_HULL:
            e.notify("ship", "not enough alien alloy")
            return False
        e.stores_add("alien alloy", -ALLOY_PER_HULL)
        e.set("game", "spaceShip", "hull", value=self.hull() + 1)
        e.emit("sound", "reinforceHull")
        return True

    def upgrade_engine(self) -> bool:
        e = self.e
        if e.stores_get("alien alloy") < ALLOY_PER_THRUSTER:
            e.notify("ship", "not enough alien alloy")
            return False
        e.stores_add("alien alloy", -ALLOY_PER_THRUSTER)
        e.set("game", "spaceShip", "thrusters", value=self.thrusters() + 1)
        e.emit("sound", "upgradeEngine")
        return True

    def lift_off(self) -> bool:
        """Victory. Sets `lifted_off`; the app reads this to show ending."""
        e = self.e
        if not self.can_lift_off():
            e.notify("ship", "the ship's hull will not hold")
            return False
        self.lifted_off = True
        e.notify(
            "ship",
            "the ship lifts off through the haze. above the clouds, the stars.",
        )
        e.emit("sound", "liftOff")
        e.emit("lift_off")
        return True
