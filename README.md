# Adaptive Traffic Signal Control System

A four-way intersection is simulated in **SUMO**. **Python** (via **TraCI**) reads the traffic every second and stores it in **MySQL**. At every red light, **five scheduling algorithms** (ideas from OS CPU scheduling) decide which approach should get the next green. The selected algorithm's choice is applied to the real signal in SUMO, always through a safe yellow → all-red → green sequence. Ambulances can interrupt the schedule. **matplotlib** shows everything live and saves charts at the end.

## How one second works

```text
 SUMO moves vehicles ─► monitor counts each approach ─► INSERT into MySQL (traffic_snapshots)
                                                                   │
                       SELECT latest state from MySQL ◄────────────┘
                                   │
                ambulance waiting? ── yes ─► preempt (hold green / cut green safely)
                                   │ no
                         green time over? ── yes ─► RED LIGHT: all 5 algorithms vote ─► votes table
                                                       selected one applied ─► yellow 3 s ─► all-red 1 s ─► green
```

Only one approach is ever green. Python never skips yellow or all-red, not even for an ambulance.

## The five algorithms

| Algorithm | OS idea | How it picks the next green | Green time |
|---|---|---|---|
| **Fixed** | none (baseline) | Next approach in N → E → S → W order, even if empty | 30 s |
| **FCFS** | First Come First Served | The approach whose queue formed first | 10 s + 2 s per queued vehicle (10–30 s) |
| **Round Robin** | time slicing | Next *non-empty* approach in N → E → S → W order | 20 s quantum |
| **Priority + Aging** | priority scheduling with aging | Score = 3·trucks + 2·cars + 1·bikes + queue + 1 point per second waited | 10–30 s, as FCFS |
| **Hybrid** | adaptive / multilevel | Looks at the traffic and uses the best-suited rule (below) | 10–30 s |

Hybrid rules, checked in order:
1. **Starvation guard:** an approach unserved for 120 s goes first.
2. **Light traffic** (≤ 6 vehicles halted in total): use **FCFS**.
3. **Imbalanced** (busiest queue ≥ 1.5 × average): use **Priority + Aging**.
4. **Otherwise** (evenly busy): use **Round Robin**, with the slice sized to the queue.

**All five vote at every red light** (`src/schedulers.py → vote_all`). You choose which one *controls* the light with `--scheduler`. The others are recorded for comparison in the terminal, the live window and the `votes` table.

## Emergency vehicles (`--ambulances`)

Adds 7 ambulances (`simulation/routes/emergency.rou.xml`). They stop at red lights like everyone else, so any priority they get comes from our controller, which works like an **OS interrupt**:

- **The ambulance's approach is already green:** keep it green until the ambulance passes (at most 60 s).
- **Another approach is green:** let it run at least 5 s, then yellow → all-red → green for the ambulance.
- **During yellow or all-red:** the next green is redirected to the ambulance.
- **Several ambulances:** the one nearest the stop line goes first.

## Run it

Requirements: Python 3.10+, SUMO (with `sumo`/`sumo-gui` on PATH), and MySQL 8.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
mysql -u root -p < schema.sql          # creates the traffic_control database (6 tables)
Copy-Item .env.example .env            # then put your MySQL password in .env
```

```powershell
# watch it: SUMO-GUI + live matplotlib dashboard
python -m src.main --scenario moderate --scheduler hybrid --gui

# ambulances
python -m src.main --scenario moderate --scheduler hybrid --ambulances --gui

# compare all five on the same traffic (one run each, then a comparison table + chart)
python -m src.main --scenario peak --scheduler all --no-live
```

| Option | Meaning |
|---|---|
| `--scenario` | `light` (6 cars), `moderate` (busy, below capacity), `peak` (light → rush hour → moderate), `asymmetric` (north overloaded), `heavy` (all overloaded) |
| `--scheduler` | `fixed`, `fcfs`, `round_robin`, `priority_aging`, `hybrid`, or `all` |
| `--seed` | random seed (same seed = same traffic, for fair comparisons) |
| `--duration` | simulated seconds (default 400) |
| `--ambulances` | add the 7 ambulances |
| `--gui` | open SUMO-GUI |
| `--no-live` | skip the live matplotlib window (much faster) |
| `--quiet` | print only the results, not one line per red light |

### What you see in the terminal

```text
 t=137s  E->W  green 30s  | votes Fixed:S  FCFS:W  RR:S  P+A:W  Hybrid:W*  | queues N9 E0 S4 W10
 t=151s  AMBULANCE on east: ending west green early -> yellow -> all-red -> east
```
Each line is one red light: the green moves from East to West for 30 s. `votes` shows each algorithm's choice, and `*` marks the one in control. `queues` are the halted vehicles per approach. A short results block follows each run, and a table follows `--scheduler all`.

### Charts (matplotlib)

- **Live window** during the run: queue per approach, the junction with its current lights and ambulances, the last red light's votes, and how often each algorithm agrees with the applied choice.
- **`outputs/run_<id>.png`** after each run: queues over time, signal timeline with ambulances, agreement between algorithms, and key results.
- **`outputs/compare_<scenario>_seed<seed>.png`** after `--scheduler all`: one panel per metric (waiting time, queue, max queue, vehicles completed, phase switches, ambulance delay).
- Redraw any chart from MySQL: `python -m src.charts --run 12` or `python -m src.charts --compare peak --seed 42`.

## Project files

```text
schema.sql            MySQL tables (run once)
queries.sql           ready-made queries for the demo (votes per red light, safety sequence, ambulances)
src/config.py         every tunable number (timings, weights, thresholds)
src/main.py           command line + the one-second simulation loop + results
src/monitor.py        reads each approach from SUMO: vehicles, queue, vehicle types, ambulances
src/database.py       all MySQL reads/writes (parameterised queries)
src/schedulers.py     the 5 algorithms + vote_all()
src/controller.py     the traffic light: green -> yellow -> all-red, red-light voting, ambulance preemption
src/dashboard.py      live matplotlib window
src/charts.py         saved matplotlib charts from MySQL
simulation/           SUMO network (one 4-way junction, left-hand traffic) and traffic scenarios
docs/                 architecture diagram and database ER diagram
```

## Database (`traffic_control`, 6 tables)

| Table | One row per… | Holds |
|---|---|---|
| `runs` | simulation run | scenario, scheduler in control, seed, and final results |
| `traffic_snapshots` | approach per second | vehicles, queue, oldest wait, cars/trucks/bikes/ambulances. **The schedulers read this.** |
| `decisions` | red light | from → to approach, green time, who decided (scheduler or `emergency`), reason |
| `votes` | algorithm per red light | what each of the 5 algorithms chose, its score, and whether it was applied |
| `signal_events` | light change | every green / yellow / all-red sent to SUMO |
| `ambulances` | ambulance per run | when it was detected, got green, and crossed |

See [docs/database_er_diagram.md](docs/database_er_diagram.md).

## Metrics

- **Average waiting time:** SUMO's `waitingTime` averaged over vehicles that completed their trip.
- **Average / maximum queue:** halted vehicles per approach, sampled every second.
- **Vehicles completed (throughput):** trips finished by the end of the run.
- **Phase switches:** how many times the green moved to a different approach. Each switch costs 4 s of yellow + all-red.
- **Ambulance delay:** time each ambulance lost compared with an empty road (SUMO `timeLoss + departDelay`).

## Notes and limits

- Simulation only: one intersection, one straight-through lane per approach, no turning.
- One run per seed is noisy, so compare schedulers over several seeds before drawing conclusions. Average waiting time (s) over seeds 1–5, 400 s, no ambulances:

  | Scenario | Fixed | FCFS | Round Robin | Priority + Aging | Hybrid |
  |---|---:|---:|---:|---:|---:|
  | light | 23.7 | 17.1 | 30.4 | **16.8** | 17.1 |
  | moderate | 48.3 | 38.3 | 44.6 | **36.3** | 36.5 |
  | peak | 41.9 | **32.3** | 39.2 | 35.3 | 33.5 |
  | asymmetric | 80.6 | 78.8 | 83.8 | **78.1** | 82.0 |
  | heavy | 107.8 | 107.9 | 109.4 | 108.8 | **107.5** |

  Under capacity, the adaptive algorithms clearly beat Fixed. Hybrid is always close to the best, but not significantly better than FCFS or Priority + Aging.
- `heavy` and `asymmetric` exceed the junction's capacity, so every algorithm gives similar results there.
- Ambulances cannot overtake in a single lane. Even with an immediate green, they wait for the cars ahead to move.
