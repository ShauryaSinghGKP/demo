"""All MySQL access. Every query is parameterised (%s), never built by string formatting."""

import os
from pathlib import Path

import mysql.connector

from src.config import ROOT

SNAPSHOT_COLUMNS = ("vehicles", "queue", "oldest_wait_sec", "cars", "trucks", "bikes",
                    "ambulances", "ambulance_distance_m")


def _read_env() -> None:
    """Load DB_HOST / DB_USER / DB_PASSWORD ... from the git-ignored .env file."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class Database:
    def __init__(self):
        _read_env()
        self.conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "traffic_control"), autocommit=True)

    def _execute(self, sql: str, params: tuple = ()) -> int:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        new_id = cur.lastrowid
        cur.close()
        return new_id

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    def close(self) -> None:
        self.conn.close()

    # ---- runs ---------------------------------------------------------------------------
    def start_run(self, scenario: str, scheduler: str, seed: int, duration: int, ambulances: bool) -> int:
        return self._execute("INSERT INTO runs (scenario, scheduler, seed, duration_sec, ambulances_on) "
                             "VALUES (%s, %s, %s, %s, %s)", (scenario, scheduler, seed, duration, ambulances))

    def finish_run(self, run_id: int, results: dict | None) -> None:
        if results is None:
            self._execute("UPDATE runs SET status='failed' WHERE run_id=%s", (run_id,))
            return
        self._execute("""UPDATE runs SET status='completed', avg_wait_sec=%s, avg_queue=%s, max_queue=%s,
                         throughput=%s, phase_switches=%s, ambulance_delay_sec=%s WHERE run_id=%s""",
                      (results["avg_wait_sec"], results["avg_queue"], results["max_queue"], results["throughput"],
                       results["phase_switches"], results["ambulance_delay_sec"], run_id))

    # ---- traffic snapshots (monitor -> MySQL -> schedulers) -----------------------------------
    def save_snapshot(self, run_id: int, now: int, rows: list[dict]) -> None:
        cur = self.conn.cursor()
        cur.executemany(
            f"INSERT INTO traffic_snapshots (run_id, sim_time, approach, {', '.join(SNAPSHOT_COLUMNS)}) "
            f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(SNAPSHOT_COLUMNS))})",
            [(run_id, now, r["approach"], *(r[c] for c in SNAPSHOT_COLUMNS)) for r in rows])
        cur.close()

    def latest_state(self, run_id: int) -> dict[str, dict]:
        """The schedulers' only input: the newest snapshot of every approach, read back from MySQL."""
        rows = self.query("""SELECT * FROM traffic_snapshots
                             WHERE run_id = %s AND sim_time = (SELECT MAX(sim_time) FROM traffic_snapshots
                                                               WHERE run_id = %s)""", (run_id, run_id))
        return {r["approach"]: r for r in rows}

    # ---- decisions, votes and signal changes --------------------------------------------------
    def save_decision(self, run_id: int, now: int, from_approach: str, to_approach: str, green: int,
                      decided_by: str, reason: str, votes: dict | None) -> None:
        decision_id = self._execute(
            "INSERT INTO decisions (run_id, sim_time, from_approach, to_approach, green_sec, decided_by, reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)", (run_id, now, from_approach, to_approach, green, decided_by,
                                                   reason[:200]))
        if votes:
            cur = self.conn.cursor()
            cur.executemany("INSERT INTO votes VALUES (%s, %s, %s, %s, %s, %s)",
                            [(decision_id, name, v["approach"], v["green"], v["score"], name == decided_by)
                             for name, v in votes.items()])
            cur.close()

    def save_signal(self, run_id: int, now: int, approach: str, state: str, note: str) -> None:
        self._execute("INSERT INTO signal_events (run_id, sim_time, approach, state, note) VALUES (%s,%s,%s,%s,%s)",
                      (run_id, now, approach, state, note[:200]))

    # ---- ambulances -----------------------------------------------------------------------
    def ambulance_detected(self, run_id: int, vehicle: str, approach: str, now: int, green_now: bool) -> None:
        self._execute("INSERT IGNORE INTO ambulances (run_id, vehicle_id, approach, detected_at, green_at) "
                      "VALUES (%s, %s, %s, %s, %s)", (run_id, vehicle, approach, now, now if green_now else None))

    def ambulance_got_green(self, run_id: int, approach: str, now: int) -> None:
        self._execute("UPDATE ambulances SET green_at=%s WHERE run_id=%s AND approach=%s AND green_at IS NULL",
                      (now, run_id, approach))

    def ambulance_crossed(self, run_id: int, vehicle: str, now: int) -> None:
        self._execute("UPDATE ambulances SET crossed_at=%s WHERE run_id=%s AND vehicle_id=%s",
                      (now, run_id, vehicle))
