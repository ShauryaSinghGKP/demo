# PPT Generation Context: Adaptive Traffic Signal Control System

Factual background for building the presentation. Separate implemented features from future work. Do not invent team details, mentor feedback, or results.

## Overview

- College PBL in Operating Systems + DBMS, team LampLighters (OSDBMS-V-2026-T264).
- Goal: a simulated adaptive traffic signal that observes four approaches, chooses the next green with OS-style scheduling algorithms, and records everything in MySQL.
- Stack: SUMO / SUMO-GUI, Python, TraCI, MySQL, matplotlib.
- One four-way junction with left-hand traffic and one straight-through lane per approach (North, East, South, West). Vehicle classes: car, truck, motorcycle, ambulance.

## How it works (one simulated second)

```text
SUMO step -> monitor counts each approach -> INSERT traffic_snapshots (MySQL)
          -> SELECT latest state -> ambulance check -> if green time is over: RED LIGHT
          -> all 5 algorithms vote (votes table) -> selected one applied
          -> yellow 3 s -> all-red 1 s -> green (via TraCI) -> SUMO
```

## Implemented

- **Five algorithms, all voting at every red light:**
  - Fixed: 30 s rotation.
  - FCFS: oldest queue first.
  - Round Robin: next non-empty approach, 20 s quantum.
  - Priority + Aging: 3·trucks + 2·cars + 1·bikes + queue + 1 point per second waited.
  - Hybrid: starvation guard at 120 s; light traffic → FCFS; imbalanced → Priority + Aging; balanced → Round Robin.
- Adaptive green length: 10 s + 2 s per queued vehicle, kept between 10 and 30 s.
- `--scheduler` selects which algorithm controls the light. The other four are recorded for live comparison. `--scheduler all` runs each one on the same traffic and compares them.
- **Safety:** only one approach is green at a time, and yellow + all-red are never skipped. SUMO's real signal matched the controller at every second in testing.
- **Emergency preemption (interrupt):**
  - If the ambulance's approach is green, hold it (at most 60 s).
  - If another approach is green, cut it after at least 5 s, via yellow and all-red.
  - During clearance, redirect the next green to the ambulance.
  - With several ambulances, the nearest goes first.
  - Each ambulance's detected → green → crossed times are stored.
- **MySQL `traffic_control`, 6 tables:** runs, traffic_snapshots, decisions, votes, signal_events, ambulances. Demo queries are in `queries.sql`.
- **matplotlib:** a live dashboard (queues, junction lights, votes, agreement) and saved charts (per-run detail, multi-metric comparison).
- **Terminal:** one compact line per red light (all votes + queues) and a short results block.
- Five traffic scenarios: light, moderate, peak, asymmetric, heavy.

## Results (seeds 1-5, 400 s, average waiting time in seconds)

| Scenario | Fixed | FCFS | Round Robin | Priority + Aging | Hybrid |
|---|---:|---:|---:|---:|---:|
| Light | 23.7 | 17.1 | 30.4 | 16.8 | 17.1 |
| Moderate | 48.3 | 38.3 | 44.6 | 36.3 | 36.5 |
| Peak | 41.9 | 32.3 | 39.2 | 35.3 | 33.5 |
| Asymmetric | 80.6 | 78.8 | 83.8 | 78.1 | 82.0 |
| Heavy | 107.8 | 107.9 | 109.4 | 108.8 | 107.5 |

- Under capacity (light/moderate/peak), adaptive algorithms cut waiting time by about 6–12 s compared with Fixed.
- Hybrid is close to the best everywhere but not significantly better than FCFS or Priority + Aging.
- Overloaded scenarios (asymmetric/heavy) exceed the junction's capacity, so all algorithms perform similarly.

## Limits / future work

- Simulation only. One junction, no turning movements, and no multi-lane approaches.
- Ambulances cannot overtake within one lane.
- More seeds and statistical testing would strengthen the comparison.
