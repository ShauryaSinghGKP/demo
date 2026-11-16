-- Useful queries for the demo / viva.   USE traffic_control;  then run any block.
USE traffic_control;

-- 1. All runs with their results (newest first)
SELECT run_id, scenario, scheduler, seed, ambulances_on, status,
       avg_wait_sec, avg_queue, max_queue, throughput, phase_switches, ambulance_delay_sec
FROM runs ORDER BY run_id DESC;

-- 2. What the sensors saw at one moment (the exact input the schedulers read)
SELECT approach, vehicles, queue, oldest_wait_sec, cars, trucks, bikes, ambulances, ambulance_distance_m
FROM traffic_snapshots
WHERE run_id = (SELECT MAX(run_id) FROM runs) AND sim_time = 120;

-- 3. Every red light of the latest run, with what ALL five algorithms voted (one row per red light)
SELECT d.sim_time, d.from_approach, d.to_approach, d.green_sec, d.decided_by,
       MAX(CASE WHEN v.algorithm = 'fixed'          THEN v.chosen_approach END) AS fixed,
       MAX(CASE WHEN v.algorithm = 'fcfs'           THEN v.chosen_approach END) AS fcfs,
       MAX(CASE WHEN v.algorithm = 'round_robin'    THEN v.chosen_approach END) AS round_robin,
       MAX(CASE WHEN v.algorithm = 'priority_aging' THEN v.chosen_approach END) AS priority_aging,
       MAX(CASE WHEN v.algorithm = 'hybrid'         THEN v.chosen_approach END) AS hybrid
FROM decisions d LEFT JOIN votes v USING (decision_id)
WHERE d.run_id = (SELECT MAX(run_id) FROM runs)
GROUP BY d.decision_id ORDER BY d.sim_time;

-- 4. How often each algorithm agreed with the applied choice (latest run)
SELECT v.algorithm, COUNT(*) AS red_lights,
       ROUND(100 * AVG(v.chosen_approach <=> d.to_approach), 1) AS agreed_pct
FROM votes v JOIN decisions d USING (decision_id)
WHERE d.run_id = (SELECT MAX(run_id) FROM runs)
GROUP BY v.algorithm;

-- 5. Safety check: every green must come after yellow -> all_red (shows the full light sequence)
SELECT sim_time, approach, state, note
FROM signal_events WHERE run_id = (SELECT MAX(run_id) FROM runs) ORDER BY event_id;

-- 6. Ambulances: detected -> got green -> crossed, and how long each step took
SELECT vehicle_id, approach, detected_at, green_at, crossed_at,
       green_at - detected_at   AS seconds_until_green,
       crossed_at - detected_at AS seconds_on_approach
FROM ambulances WHERE run_id = (SELECT MAX(run_id) FROM runs WHERE ambulances_on) ORDER BY detected_at;

-- 7. Emergency decisions (ambulance overrides of the scheduler)
SELECT run_id, sim_time, from_approach, to_approach, reason
FROM decisions WHERE decided_by = 'emergency' ORDER BY run_id DESC, sim_time;

-- 8. Average result per scheduler over all completed runs of one scenario
SELECT scheduler, COUNT(*) AS runs, ROUND(AVG(avg_wait_sec), 2) AS avg_wait,
       ROUND(AVG(throughput), 1) AS avg_completed, ROUND(AVG(phase_switches), 1) AS avg_switches
FROM runs WHERE status = 'completed' AND scenario = 'moderate' AND NOT ambulances_on
GROUP BY scheduler ORDER BY avg_wait;
