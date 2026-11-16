# Chat Handoff: Adaptive Traffic Signal Control

Project root: `D:\codes\PBL 5th sem`. Use `.venv\Scripts\python.exe`. College PBL (OS + DBMS) by team LampLighters (OSDBMS-V-2026-T264). The Phase-III report PDF is in the root (`PHASE 3 Report.pdf`).

## State after the 2026-11-14 simplification

The project was rewritten into a flat, explainable structure (about 750 lines of Python). The pre-simplification code (Phase-3 version with experiments runner, tests, `best` mode, old schema) is backed up at `D:\codes\PBL5_backup_before_simplify_2026-11-14`.

```
schema.sql / queries.sql        MySQL database `traffic_control` (6 tables) + demo queries
src/config.py                   all parameters
src/main.py                     CLI + 1-second loop + results/comparison printing
src/monitor.py                  TraCI -> per-approach state (vehicles, queue, oldest wait, classes, ambulances)
src/database.py                 all MySQL access
src/schedulers.py               fixed, fcfs, round_robin, priority_aging, hybrid + vote_all()
src/controller.py               signal state machine, red-light voting, ambulance preemption, AmbulanceTracker
src/dashboard.py                live matplotlib window (TkAgg)
src/charts.py                   saved charts from MySQL (run_<id>.png, compare_<scenario>_seed<seed>.png)
```

- Every second: SUMO step -> monitor -> INSERT traffic_snapshots -> SELECT latest state -> controller.step.
- At every red light **all 5 algorithms vote** (votes table, terminal line, live window); `--scheduler` picks which one controls. `--scheduler all` runs the five one after another and prints/saves a comparison.
- Safety: one green at a time; 3 s yellow + 1 s all-red always. Verified 0 mismatches between SUMO's real phase and controller state across all schedulers with ambulances.
- Hybrid: starvation guard 120 s (was 90 s in the old version, which misfired under overload) > light (<= 6 halted) FCFS > imbalanced (max >= 1.5 x mean) P+A > balanced RR with queue-sized slice.
- Ambulances (`--ambulances`): on-lane detection only (upstream backlog detection was removed for simplicity); hold green (max 60 s), cut a conflicting green after >= 5 s, redirect during yellow/all-red, nearest first. There is no longer a `--no-preemption` baseline flag.
- Old database `adaptive_traffic` (~900 runs) is untouched as an archive; `.env` now points at `traffic_control`.
- Removed: experiments runner, unit tests, `best` mode, inclusive/unfinished metrics, pandas/sumolib dependencies.

## Current results (seeds 1-5, 400 s, no ambulances, average waiting time s)

| Scenario | Fixed | FCFS | RR | P+A | Hybrid |
|---|---:|---:|---:|---:|---:|
| light | 23.7 | 17.1 | 30.4 | 16.8 | 17.1 |
| moderate | 48.3 | 38.3 | 44.6 | 36.3 | 36.5 |
| peak | 41.9 | 32.3 | 39.2 | 35.3 | 33.5 |
| asymmetric | 80.6 | 78.8 | 83.8 | 78.1 | 82.0 |
| heavy | 107.8 | 107.9 | 109.4 | 108.8 | 107.5 |

These 125 runs are stored in `traffic_control`. Adaptive policies clearly beat Fixed under capacity; Hybrid is close to the best but not significantly better than FCFS/P+A.

## Working guidance

- Inspect the current code before describing it; do not present planned work as done.
- Do not claim improvements without repeated-seed runs.
- Never put the DB password in docs or commits (it lives in the git-ignored `.env`).
- Legacy charts under `outputs/figures` came from the previous version and have been removed. Generated reports/results are ignored and not committed.
