# Decisions — dark-room-tui

## Port vs Subprocess (Stage 1)

**Decision: port to Python.**

A Dark Room is ~8,500 LOC of JS with heavy jQuery DOM manipulation. The
game logic is interleaved with view updates throughout (every state change
triggers a `$('#...')` UI mutation). Extracting a clean JS-core-only build
to drive from Python would require invasive surgery of the same magnitude
as porting the logic cleanly.

Porting gives us:

- Deterministic state transitions (RNG seeded for QA).
- Zero subprocess latency; native asyncio integration with Textual.
- Trivial state snapshots for QA / agent API.
- Full control over the tick scheduler (we simulate timers in-process).

The reference engine is preserved under `vendor/adarkroom/` for ongoing
comparison, and the `audio/` FLACs are reused verbatim (Phase D).

## Aesthetic (Stage 3)

The original ADR uses a vertical single-column layout with a sidebar of
stores. A 4-panel SimCity-style layout would violate the game's sparse
intent. Layout for the TUI:

```
┌─ Title / Tabs ─────────────────────────────────────┐
├──────────────────────────┬─────────────────────────┤
│  Active location view    │  Stores panel           │
│  (Room / Outside / Path  │  (wood, fur, meat, ...) │
│   / World / Ship)        │  + income tooltips      │
│                          │                         │
├──────────────────────────┴─────────────────────────┤
│  Event log (RichLog)                               │
└────────────────────────────────────────────────────┘
```

Buttons are keyboard-first with visible letter hotkeys. Cooldowns render
as progress bars.

## Scope (v1 session)

**In:** Room (fire, builder, craft/build/buy), Outside (village, workers,
traps, gather), Path (outfitting, embark), World (map, movement, food/
water, combat), Ship → victory, core events. Sound via vendor FLACs.

**Out (v2+):** Space shooter minigame, prestige/scoring, Dropbox sync,
full 200+ event tree (we ship the common-path subset). Fabricator crafting
stubbed.

## Randomness

Single `random.Random` instance attached to `Engine`. Tests seed it to
`42` before running each scenario so event rolls + combat are
deterministic.

## Timer model

JS ADR uses `setTimeout` with wall-clock delays. We translate to a single
`Engine.tick(dt)` scheduler that advances a priority queue of
`(due_time, callback)` entries. Each Textual `set_interval(0.1)` calls
`engine.advance(0.1)` which fires all due timers. Gives us a fast-forward
mode for tests (`engine.advance(60.0)` runs a game-minute instantly).
