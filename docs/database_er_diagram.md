# Database ER Diagram: `traffic_control`

Source: [`schema.sql`](../schema.sql). Six tables. Every table except `votes` hangs off `runs`; `votes` hangs off `decisions`. Deleting a run deletes everything recorded for it (`ON DELETE CASCADE`).

```mermaid
erDiagram
    RUNS ||--o{ TRAFFIC_SNAPSHOTS : "observed every second"
    RUNS ||--o{ DECISIONS : "one per red light"
    DECISIONS ||--o{ VOTES : "5 algorithms vote"
    RUNS ||--o{ SIGNAL_EVENTS : "light changes"
    RUNS ||--o{ AMBULANCES : "ambulance lifecycle"

    RUNS {
        INT run_id PK
        VARCHAR scenario
        VARCHAR scheduler "algorithm in control"
        INT seed
        INT duration_sec
        BOOLEAN ambulances_on
        ENUM status "running | completed | failed"
        TIMESTAMP started_at
        DECIMAL avg_wait_sec "result"
        DECIMAL avg_queue "result"
        INT max_queue "result"
        INT throughput "result"
        INT phase_switches "result"
        DECIMAL ambulance_delay_sec "result"
    }
    TRAFFIC_SNAPSHOTS {
        BIGINT snapshot_id PK
        INT run_id FK
        INT sim_time
        ENUM approach "north | east | south | west"
        INT vehicles
        INT queue
        INT oldest_wait_sec
        INT cars
        INT trucks
        INT bikes
        INT ambulances
        DECIMAL ambulance_distance_m "NULL if none"
    }
    DECISIONS {
        INT decision_id PK
        INT run_id FK
        INT sim_time
        ENUM from_approach
        ENUM to_approach
        INT green_sec
        VARCHAR decided_by "scheduler or emergency"
        VARCHAR reason
    }
    VOTES {
        INT decision_id PK,FK
        VARCHAR algorithm PK
        ENUM chosen_approach "NULL = no traffic"
        INT green_sec
        DECIMAL score
        BOOLEAN applied
    }
    SIGNAL_EVENTS {
        BIGINT event_id PK
        INT run_id FK
        INT sim_time
        ENUM approach
        ENUM state "green | yellow | all_red"
        VARCHAR note
    }
    AMBULANCES {
        INT run_id PK,FK
        VARCHAR vehicle_id PK
        ENUM approach
        INT detected_at
        INT green_at "NULL until it gets green"
        INT crossed_at "NULL until it crosses"
    }
```

## Keys and constraints

- **Primary keys:** surrogate `AUTO_INCREMENT` ids, except two composite keys. `votes (decision_id, algorithm)` allows exactly one vote per algorithm per red light, and `ambulances (run_id, vehicle_id)` allows one row per ambulance per run.
- **Unique:** `traffic_snapshots (run_id, sim_time, approach)` allows one reading per approach per second.
- **Indexes:** `decisions (run_id, sim_time)` and `signal_events (run_id, sim_time)` for timeline queries.
- **ENUMs** restrict approaches to `north/east/south/west`, light states to `green/yellow/all_red`, and run status to `running/completed/failed`.
- **Why `votes` is a separate table:** each red light has five votes. Storing them as rows instead of five column groups keeps the table in first normal form. It also makes "how often did algorithm X agree?" a simple `GROUP BY` (see `queries.sql` #4).
- **Emergency decisions** (`decided_by = 'emergency'`) have no votes, because the ambulance overrides the schedulers.
