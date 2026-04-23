# DOGFOOD — dark-room

_Session: 2026-04-23T12:41:36, driver: pty, duration: 3.0 min_

**PASS** — ran for 1.9m, captured 9 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 31 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 1 coverage note(s) — see Coverage section.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)

_None._

## Coverage

- Driver backend: `pty`
- Keys pressed: 949 (unique: 40)
- State samples: 46 (unique: 31)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=82.9, B=10.5, C=18.1
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/dark-room-20260423-123943`

Unique keys exercised: /, 1, 2, 3, 4, 5, :, ?, H, R, ], c, down, e, enter, escape, f2, g, h, i, k, l, left, m, n, o, p, question_mark, r, right, s, shift+slash, shift+tab, space, t, u, up, v, w, z

### Coverage notes

- **[CN1] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `dark-room-20260423-123943/milestones/first_input.txt` | key=l |
