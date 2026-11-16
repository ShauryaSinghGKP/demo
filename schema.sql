
CREATE DATABASE traffic_control;
USE traffic_control;

CREATE TABLE runs (
    run_id            INT AUTO_INCREMENT PRIMARY KEY,
    scenario          VARCHAR(20)  NOT NULL,
    scheduler         VARCHAR(20)  NOT NULL,           -- the algorithm that controlled the light
    seed              INT          NOT NULL,
    duration_sec      INT          NOT NULL,
    ambulances_on     BOOLEAN      NOT NULL DEFAULT FALSE,
    status            ENUM('running', 'completed', 'failed') NOT NULL DEFAULT 'running',
    started_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    avg_wait_sec      DECIMAL(8,2) NULL,              -- SUMO tripinfo waitingTime, completed trips
    avg_queue         DECIMAL(8,2) NULL,              -- halted vehicles, averaged over approaches and seconds
    max_queue         INT          NULL,
    throughput        INT          NULL,              -- vehicles that completed their trip
    phase_switches    INT          NULL,              -- times the green moved to another approach
    ambulance_delay_sec DECIMAL(8,2) NULL             -- average seconds an ambulance lost vs free flow
);

CREATE TABLE traffic_snapshots (
    snapshot_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id            INT          NOT NULL,
    sim_time          INT          NOT NULL,
    approach          ENUM('north', 'east', 'south', 'west') NOT NULL,
    vehicles          INT          NOT NULL,          -- vehicles on the approach road
    queue             INT          NOT NULL,          -- halted vehicles (speed < 0.1 m/s)
    oldest_wait_sec   INT          NOT NULL,          -- how long the current queue has existed
    cars              INT          NOT NULL,
    trucks            INT          NOT NULL,
    bikes             INT          NOT NULL,
    ambulances        INT          NOT NULL,
    ambulance_distance_m DECIMAL(6,1) NULL,           -- nearest ambulance to the stop line
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    UNIQUE KEY one_row_per_second (run_id, sim_time, approach)
);

CREATE TABLE decisions (
    decision_id       INT AUTO_INCREMENT PRIMARY KEY,
    run_id            INT          NOT NULL,
    sim_time          INT          NOT NULL,
    from_approach     ENUM('north', 'east', 'south', 'west') NOT NULL,
    to_approach       ENUM('north', 'east', 'south', 'west') NOT NULL,
    green_sec         INT          NOT NULL,
    decided_by        VARCHAR(20)  NOT NULL,          -- scheduler name, or 'emergency'
    reason            VARCHAR(200) NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    INDEX (run_id, sim_time)
);

CREATE TABLE votes (
    decision_id       INT          NOT NULL,
    algorithm         VARCHAR(20)  NOT NULL,
    chosen_approach   ENUM('north', 'east', 'south', 'west') NULL,   -- NULL = no traffic anywhere
    green_sec         INT          NOT NULL,
    score             DECIMAL(10,2) NOT NULL,
    applied           BOOLEAN      NOT NULL,          -- TRUE for the algorithm that controlled the light
    PRIMARY KEY (decision_id, algorithm),
    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id) ON DELETE CASCADE
);

CREATE TABLE signal_events (
    event_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id            INT          NOT NULL,
    sim_time          INT          NOT NULL,
    approach          ENUM('north', 'east', 'south', 'west') NOT NULL,
    state             ENUM('green', 'yellow', 'all_red') NOT NULL,
    note              VARCHAR(200) NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    INDEX (run_id, sim_time)
);

CREATE TABLE ambulances (
    run_id            INT          NOT NULL,
    vehicle_id        VARCHAR(40)  NOT NULL,
    approach          ENUM('north', 'east', 'south', 'west') NOT NULL,
    detected_at       INT          NOT NULL,
    green_at          INT          NULL,
    crossed_at        INT          NULL,
    PRIMARY KEY (run_id, vehicle_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
