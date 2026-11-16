# Adaptive Traffic Signal Control: Changes, Contents and How to Run

Team LampLighters (OSDBMS-V-2026-T264). This file records all the work done after the Phase-II code: what was built, what was removed, what was kept, how to run everything, and the results.

---

## 1. Summary

Work happened in two steps:

1. **Phase-III features (12 Nov 2026).** Added a Hybrid scheduler, ambulance (emergency vehicle) priority, two new traffic scenarios, multi-seed experiments and matplotlib charts.
2. **Simplification (14 Nov 2026).** Rewrote the whole project into a small, flat set of files that is easy to explain. It keeps every scheduler and both Phase-III features. All five algorithms now vote at every red light in real time. There is a new, simpler MySQL database, a live matplotlib dashboard, and a cleaner terminal.

The current project is the simplified version. The code from the end of step 1 is backed up (see section 9).

---

## 2. How the system works now

Every simulated second:

```text
 1. SUMO moves the vehicles one step
 2. monitor.py counts each approach (vehicles, queue, oldest wait, cars/trucks/bikes/ambulances)
 3. database.py INSERTs that into MySQL  -> traffic_snapshots
 4. database.py SELECTs the latest state back from MySQL   (the schedulers only see SQL data)
 5. controller.py:
      - ambulance waiting?   -> emergency preemption (hold green / cut green safely / redirect)
      - green time over?     -> RED LIGHT: all 5 algorithms vote -> saved in decisions + votes
                                the algorithm chosen with --scheduler is applied
                                -> yellow 3 s -> all-red 1 s -> next green   (sent to SUMO by TraCI)
 6. dashboard.py redraws the live matplotlib window
```

Safety rule: exactly one approach is green at a time. A green always ends with 3 s yellow + 1 s all-red. Nothing skips this, not even an ambulance.

---

## 3. What was done, step by step

### Step 1: Phase-III features (12 Nov)

| Work | Details |
|---|---|
| Hybrid scheduler | Chooses a sub-policy from the live traffic state: starvation guard, then FCFS (light traffic), Priority + Aging (imbalanced) or Round Robin (balanced). |
| Emergency vehicles | 7 ambulances in `simulation/routes/emergency.rou.xml`. The controller detects them and preempts the signal without skipping yellow/all-red. Each ambulance's lifecycle was logged. |
| New scenarios | `moderate.rou.xml` (busy, below capacity) and `peak.rou.xml` (light → rush hour → moderate). |
| DB migration | Added an `emergency_events` table and extra columns to the old `adaptive_traffic` database. |
| Experiments | A batch runner for scenario × scheduler × seed grids with parallel workers. 250 scheduler runs and 300 emergency runs were done on held-out seeds 101–110. |
| Charts | matplotlib figures and a summary table generated from MySQL (`outputs/figures/`). |
| Tests | 10 offline unit tests. They found a real bug (the 60 s ambulance hold cap looped forever), which was fixed and all emergency runs were redone. |
| Verification | Checked every simulated second that SUMO's real light matched the controller state: 0 mismatches. |

Main Phase-III findings, from that version of the code:
- Preemption cut average ambulance delay from 53.6 s to 10.8 s (moderate) and from 58.4 s to 13.2 s (peak).
- Normal vehicles' waiting time showed no measurable increase.
- Hybrid beat Fixed in under-capacity traffic but was not clearly better than FCFS or Priority + Aging.

### Step 2: Simplification (14 Nov)

You asked for:
- simpler code with the useless parts removed,
- all schedulers checked at every red light in real time,
- a visible backend,
- a simpler MySQL schema,
- matplotlib visuals,
- an uncluttered terminal.

Your choices when asked:

| Question | Your answer |
|---|---|
| What "checks all schedulers at every red light" means | **All 5 vote, one controls.** |
| Old database | **Make a new DB and keep the old one** as an archive. |
| Features to keep | **Emergency vehicles, Hybrid scheduler** (experiments runner and unit tests were dropped). |
| Charts | **Live window + saved charts.** |

What was then done:
1. Backed up the old code (section 9).
2. Rewrote the Python into 8 flat files (section 5).
3. Wrote a new `schema.sql` with 6 simple tables in a new database, `traffic_control`, and created it.
4. Pointed `.env` and `.env.example` at `DB_NAME=traffic_control`.
5. Added the live dashboard, the saved charts and the compact terminal output.
6. Wrote `queries.sql` with demo queries.
7. Rewrote `README.md`, `docs/database_er_diagram.md`, `CHAT_CONTEXT.md` and `PPT_GENERATION_CONTEXT.md`.
8. Tested: all schedulers with ambulances gave 0 signal mismatches. Ran 125 fresh runs (5 scenarios × 5 schedulers × 5 seeds).

A bug was found and fixed during the rewrite. The approach that was currently green got a large stale "aging" bonus in Priority + Aging, so the Hybrid once kept an empty North green while East had 12 cars waiting. The green approach now counts as served "right now".

---

## 4. What was kept, removed and changed

### Kept
- All 5 algorithms: **Fixed, FCFS, Round Robin, Priority + Aging, Hybrid**.
- Their rules and timings:
  - Fixed: 30 s.
  - Round Robin: 20 s quantum.
  - FCFS, Priority + Aging and Hybrid: adaptive green of 10 s + 2 s per queued vehicle, between 10 and 30 s.
  - Priority + Aging weights: truck 3, car 2, bike 1, plus queue length, plus 1 point per second waited.
- Safety sequence: 3 s yellow + 1 s all-red, one green at a time.
- The "SQL in the loop" design. Snapshots go into MySQL every second, and the schedulers read them back from MySQL.
- **Emergency preemption:**
  - If the ambulance's approach is green, hold it (at most 60 s).
  - If another approach is green, cut it after at least 5 s, through yellow and all-red.
  - During yellow/all-red, redirect the next green to the ambulance.
  - With several ambulances, the nearest goes first.
- All SUMO files: the network and the 5 scenarios (`light`, `moderate`, `peak`, `asymmetric`, `heavy`), plus the ambulance overlay.
- `--scheduler all`: runs all five on the same traffic and compares them.
- Metrics: average waiting time, average queue, maximum queue, vehicles completed, phase switches, ambulance delay.
- The old database `adaptive_traffic`, untouched with ~900 runs.
- `docs/system_architecture.png/.svg`.

### Removed
| Removed | Why / what replaces it |
|---|---|
| `config/config.py` package | Replaced by `src/config.py` |
| `src/scheduler/` (models.py, policies.py) | Replaced by `src/schedulers.py` |
| `src/controller/` (signal_controller.py, safety.py, emergency.py) | Replaced by `src/controller.py` |
| `src/database/` (db.py, schema.sql, migrations, Queries.sql) | Replaced by `src/database.py`, `schema.sql`, `queries.sql` |
| `src/analytics/` (metrics.py, report.py) | Replaced by `src/charts.py`; metrics moved into `main.py` |
| `src/traffic_monitor.py` | Replaced by `src/monitor.py` |
| `src/experiments.py` (multi-seed runner) | Dropped, as you chose |
| `tests/` (unit tests) | Dropped, as you chose |
| `--scheduler best` mode | Dropped (it only picked a winner from old runs) |
| `--no-preemption` flag | Dropped; there is no built-in with/without-preemption comparison any more |
| `--tag` and `--gui-delay` flags | Dropped (the GUI delay is now `GUI_DELAY_MS` in config) |
| Upstream ambulance detection (ambulances stuck before entering the road) | Dropped for simplicity; ambulances are detected once they are on the approach road |
| Extra metrics (inclusive wait, unfinished vehicles, insertion backlog, civilian wait) | Dropped for simplicity |
| `pandas`, `sumolib` from requirements | No longer used |
| `docs/database_er_diagram.svg` | Showed the old tables; the Mermaid diagram in the `.md` is current |

### Changed
| Change | Before | Now |
|---|---|---|
| Scheduler decision | Only the selected algorithm decided | **All 5 vote at every red light.** The selected one is applied. Votes are shown in the terminal and live window and saved in the `votes` table. |
| Hybrid starvation limit | 90 s | **120 s.** 90 s was shorter than one overloaded cycle (3 × 34 s = 102 s), so it fired on most decisions in heavy traffic. |
| Database | `adaptive_traffic`, 7 tables, many columns | `traffic_control`, **6 simple tables** (section 6) |
| Vehicle type counts | Separate `vehicle_type_counts` table | Columns (`cars`, `trucks`, `bikes`, `ambulances`) inside `traffic_snapshots` |
| Results | Separate `performance_results` table | Result columns inside `runs` |
| Round Robin state | Kept a cursor | Stateless: "next non-empty approach after the current green", which behaves the same |
| Terminal | Large JSON blocks | One line per red light + a short results block + a comparison table |
| Charts | Report script run separately | Live window during the run + a chart saved automatically after every run / comparison |
| Run speed | About 4–8 s per headless run | About 2 s per headless run (`--no-live`) |
| Main CLI flag | `--emergency` | `--ambulances` |
| Default run | `light` / `priority_aging` | `moderate` / `hybrid` |

---

## 5. Project files now

```text
schema.sql            creates database traffic_control (6 tables); run once
queries.sql           8 demo queries (votes per red light, agreement, light sequence, ambulances, averages)
requirements.txt      traci, mysql-connector-python, matplotlib
.env / .env.example   MySQL login (DB_NAME=traffic_control); .env is git-ignored
src/config.py         every number: timings, weights, Hybrid thresholds, ambulance rules
src/main.py           command line, the one-second loop, results and the comparison table
src/monitor.py        reads each approach from SUMO through TraCI
src/database.py       all MySQL reads/writes (parameterised queries)
src/schedulers.py     fixed(), fcfs(), round_robin(), priority_aging(), hybrid(), vote_all()
src/controller.py     SignalController (green/yellow/all-red, voting, ambulance preemption) + AmbulanceTracker
src/dashboard.py      live matplotlib window
src/charts.py         saved charts from MySQL (also usable on its own)
simulation/network/   the 4-way junction (left-hand traffic, one straight lane per approach)
simulation/routes/    light, moderate, peak, asymmetric, heavy + emergency (ambulances)
docs/                 system architecture image, database ER diagram (Mermaid)
outputs/              charts produced by runs (compare_*.png, run_*.png); tripinfo/ is temporary
```

Python: about 1,040 lines including the SQL files.

---

## 6. Database `traffic_control`

| Table | One row per… | Main columns |
|---|---|---|
| `runs` | simulation run | scenario, scheduler (in control), seed, duration, ambulances_on, status, avg_wait_sec, avg_queue, max_queue, throughput, phase_switches, ambulance_delay_sec |
| `traffic_snapshots` | approach per second | sim_time, approach, vehicles, queue, oldest_wait_sec, cars, trucks, bikes, ambulances, ambulance_distance_m |
| `decisions` | red light | sim_time, from_approach, to_approach, green_sec, decided_by (scheduler or `emergency`), reason |
| `votes` | algorithm per red light | algorithm, chosen_approach, green_sec, score, applied |
| `signal_events` | light change | sim_time, approach, state (green / yellow / all_red), note |
| `ambulances` | ambulance per run | vehicle_id, approach, detected_at, green_at, crossed_at |

- `runs` is the parent of every table except `votes`, which belongs to `decisions`. All foreign keys use `ON DELETE CASCADE`.
- Composite keys: `votes (decision_id, algorithm)` and `ambulances (run_id, vehicle_id)`.
- Unique: `traffic_snapshots (run_id, sim_time, approach)`.
- The ER diagram is in `docs/database_er_diagram.md`.

---

## 7. How to run everything

### One-time setup
```powershell
cd "D:\codes\PBL 5th sem"
python -m venv .venv                      # already done on this laptop
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
mysql -u root -p < schema.sql             # creates traffic_control (already done on this laptop)
Copy-Item .env.example .env               # then set DB_PASSWORD in .env (already done on this laptop)
```
Needs Python 3.10+, SUMO (with `sumo` / `sumo-gui` on PATH), and MySQL 8.

### Run a simulation
```powershell
# Watch it: SUMO-GUI + live matplotlib dashboard
python -m src.main --scenario moderate --scheduler hybrid --gui

# With ambulances (the best demo of preemption)
python -m src.main --scenario moderate --scheduler hybrid --ambulances --gui

# Compare all five algorithms on the same traffic (fast, no live window)
python -m src.main --scenario peak --scheduler all --no-live

# Only the results, no per-red-light lines
python -m src.main --scenario heavy --scheduler fcfs --no-live --quiet
```

| Option | Values / meaning | Default |
|---|---|---|
| `--scenario` | `light`, `moderate`, `peak`, `asymmetric`, `heavy` | `moderate` |
| `--scheduler` | `fixed`, `fcfs`, `round_robin`, `priority_aging`, `hybrid`, `all` | `hybrid` |
| `--seed` | any integer; same seed = same traffic | `42` |
| `--duration` | simulated seconds | `400` |
| `--ambulances` | add the 7 ambulances | off |
| `--gui` | open SUMO-GUI | off |
| `--no-live` | skip the live matplotlib window (about 25× faster) | live window on |
| `--quiet` | hide the per-red-light lines | lines shown |

### Read the terminal
```text
 t=137s  E->W  green 30s  | votes Fixed:S  FCFS:W  RR:S  P+A:W  Hybrid:W*  | queues N9 E0 S4 W10
 t=151s  AMBULANCE on east: ending west green early -> yellow -> all-red -> east
```
- `t=137s`: simulation time.
- `E->W green 30s`: the green moves from East to West for 30 s.
- `votes`: what each algorithm picked; `*` marks the one controlling the light.
- `queues`: halted vehicles on North, East, South and West.

Each run ends with a RESULTS block. `--scheduler all` adds a COMPARISON table.

### Charts
- **Live window** (during a run unless `--no-live`):
  - halted vehicles per approach over time;
  - the junction with current light colours and ambulance flags;
  - the last red light's 5 votes, with the applied one highlighted;
  - how often each algorithm agreed with the applied choice.
- **Saved automatically:**
  - `outputs/run_<id>.png` after every run: queues, signal timeline with ambulances, agreement and results.
  - `outputs/compare_<scenario>_seed<seed>.png` after `--scheduler all`: waiting time, average queue, max queue, completed, switches, and ambulance delay when ambulances are on.
- **Redraw from MySQL at any time:**
  ```powershell
  python -m src.charts --run 12
  python -m src.charts --compare peak --seed 1
  python -m src.charts --compare moderate --seed 42 --ambulances
  ```

### See the backend in MySQL
```powershell
mysql -u root -p -t < queries.sql
```
Or open `queries.sql` in MySQL Workbench and run one block at a time:
1. all runs with results;
2. the exact input the schedulers read at one moment;
3. **every red light with all 5 votes side by side;**
4. how often each algorithm agreed;
5. the full light sequence (safety check);
6. the ambulance timeline;
7. emergency overrides;
8. average result per scheduler.

### Change parameters
Edit `src/config.py`. Examples: `RR_QUANTUM`, `FIXED_GREEN`, `TYPE_WEIGHT`, `AGING_PER_SECOND`, `HYBRID_STARVATION_SECONDS`, `EMERGENCY_MAX_HOLD`, `GUI_DELAY_MS`.

---

## 8. Verification and results

**Checks done on the simplified code:**
- A per-second check that SUMO's real light equals the controller state: **0 mismatches** across all 5 schedulers in the moderate and asymmetric scenarios with ambulances.
- SUMO-GUI launch, live dashboard, saved charts, the `charts` command and all `queries.sql` queries were each tested and work.

**Results (seeds 1–5, 400 s, no ambulances, average waiting time in seconds; stored in `traffic_control`):**

| Scenario | Fixed | FCFS | Round Robin | Priority + Aging | Hybrid |
|---|---:|---:|---:|---:|---:|
| light | 23.7 | 17.1 | 30.4 | **16.8** | 17.1 |
| moderate | 48.3 | 38.3 | 44.6 | **36.3** | 36.5 |
| peak | 41.9 | **32.3** | 39.2 | 35.3 | 33.5 |
| asymmetric | 80.6 | 78.8 | 83.8 | **78.1** | 82.0 |
| heavy | 107.8 | 107.9 | 109.4 | 108.8 | **107.5** |

How to read it:
- In under-capacity traffic, the adaptive algorithms cut waiting by about 6–12 s compared with Fixed.
- Hybrid is close to the best everywhere but not significantly better than FCFS or Priority + Aging.
- `asymmetric` and `heavy` exceed the junction's capacity, so every algorithm performs about the same.

---

## 9. Backups, old data, things to know

- **Old code backup:** `D:\codes\PBL5_backup_before_simplify_2026-11-14`. It holds the full Phase-III version with the experiments runner, tests, old schema and migrations.
- **Old database:** `adaptive_traffic` is untouched (about 900 runs).
- **Old output folders:** the legacy `outputs/figures/` charts and summary from the previous schema have been removed. `outputs/reports/` and `data/results/` retain only `.gitkeep` placeholders in the repository; generated files in those folders are ignored.
- **Git:** the project is on the `main` branch. The local working-folder ownership warning applied to an earlier checkout; it does not affect the GitHub repository.
- **Report wording:** the Phase-III PDF mentions regression tests, which the simplified project no longer contains. It also mentions the old 4-scheduler / 3-scenario setup. Adjust the wording if needed.

**Known limits:**
- Simulation only: one junction, one straight lane per approach, no turning.
- Ambulances cannot overtake in a single lane, so even with an immediate green they wait for the cars ahead to move.
- One run per seed is noisy. Compare over several seeds before claiming one algorithm is better.

---

## 10. Quick explanation for the evaluator

- **OS part:**
  - The traffic light is a shared resource. The four approaches are processes waiting for it.
  - FCFS, Round Robin (time slice) and Priority with Aging (no starvation) are CPU-scheduling algorithms.
  - Hybrid switches algorithm based on load, like an adaptive or multilevel scheduler.
  - An ambulance is an **interrupt** that preempts the current schedule.
  - Yellow + all-red is a mandatory safety section that is never skipped.
- **DBMS part:**
  - Live sensor data goes into MySQL every second, and the schedulers read their input back with SQL.
  - Every decision, every algorithm's vote, every light change and every ambulance is stored in normalised tables with keys, foreign keys and cascades.
  - `queries.sql` shows joins, aggregation, pivoting (votes per red light) and safety auditing.
- **Demo order:**
  1. `--scenario moderate --scheduler hybrid --ambulances --gui` to show SUMO, the live dashboard and the terminal votes.
  2. `queries.sql` blocks 3, 5 and 6.
  3. `--scenario peak --scheduler all --no-live` to show the comparison table and chart.
