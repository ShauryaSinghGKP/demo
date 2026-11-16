"""Run the adaptive traffic signal simulation.

    python -m src.main --scenario moderate --scheduler hybrid --gui
    python -m src.main --scenario peak --scheduler all --ambulances

Every simulated second:
    1. SUMO moves the vehicles one step
    2. the monitor counts what is waiting on each approach      -> saved to MySQL (traffic_snapshots)
    3. the latest state is read back from MySQL
    4. the controller checks for ambulances; when a green ends, all 5 algorithms vote (votes table)
       and the selected algorithm's choice goes through yellow -> all-red -> green in SUMO
"""

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

import traci

from src.config import (
    AMBULANCE_ROUTE_FILE, DEFAULT_DURATION, GUI_DELAY_MS, NETWORK_FILE, OUTPUT_DIR, SCENARIOS,
)
from src.controller import AmbulanceTracker, SignalController
from src.database import Database
from src.monitor import TrafficMonitor
from src.schedulers import ALGORITHMS
from src import charts

LINE = "-" * 96


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", choices=SCENARIOS, default="moderate")
    p.add_argument("--scheduler", choices=[*ALGORITHMS, "all"], default="hybrid",
                   help="algorithm that controls the light ('all' = run each one and compare)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--duration", type=int, default=DEFAULT_DURATION, help="simulated seconds")
    p.add_argument("--ambulances", action="store_true", help="add 7 ambulances to the traffic")
    p.add_argument("--gui", action="store_true", help="open SUMO-GUI to watch the junction")
    p.add_argument("--no-live", action="store_true", help="do not open the live matplotlib dashboard")
    p.add_argument("--quiet", action="store_true", help="hide the per-red-light lines")
    return p.parse_args()


def run_simulation(args, scheduler: str, db: Database) -> dict:
    run_id = db.start_run(args.scenario, scheduler, args.seed, args.duration, args.ambulances)
    tripinfo = OUTPUT_DIR / "tripinfo" / f"run_{run_id}.xml"
    tripinfo.parent.mkdir(parents=True, exist_ok=True)
    routes = str(SCENARIOS[args.scenario]) + (f",{AMBULANCE_ROUTE_FILE}" if args.ambulances else "")
    command = ["sumo-gui" if args.gui else "sumo", "-n", str(NETWORK_FILE), "-r", routes,
               "--seed", str(args.seed), "--end", str(args.duration), "--tripinfo-output", str(tripinfo),
               "--time-to-teleport", "-1", "--no-step-log", "--duration-log.disable", "--no-warnings"]
    if args.gui:
        command += ["--delay", str(GUI_DELAY_MS), "--start", "--quit-on-end"]

    print(f"\n{LINE}\n RUN {run_id}   scenario: {args.scenario}   in control: {scheduler}   seed: {args.seed}"
          f"   {args.duration} s   ambulances: {'on' if args.ambulances else 'off'}\n{LINE}")
    if not args.quiet:
        print(" Each line is one red light. 'votes' = what every algorithm picked (* = the one applied).")
        print(" N/E/S/W = North/East/South/West, queues = halted vehicles per approach.\n")

    monitor = TrafficMonitor()
    controller = dashboard = None
    finished = False
    try:
        traci.start(command)
        controller = SignalController(scheduler, run_id, db, verbose=not args.quiet)
        tracker = AmbulanceTracker(run_id, db)
        if not args.no_live:
            from src.dashboard import LiveDashboard          # opens a Tk window only when wanted
            dashboard = LiveDashboard(f"Run {run_id}: {args.scenario} / {scheduler} in control / seed {args.seed}")
        queue_samples = []

        while traci.simulation.getTime() < args.duration:
            traci.simulationStep()
            now = int(traci.simulation.getTime())
            rows = monitor.read(now)                                  # 2. observe
            db.save_snapshot(run_id, now, rows)                       #    -> MySQL
            state = db.latest_state(run_id)                           # 3. read back from MySQL
            controller.step(now, state)                               # 4. ambulances / votes / light change
            tracker.update(now, rows, controller.approach if controller.stage == "green" else None)
            queue_samples.extend(r["queue"] for r in rows)
            if dashboard:
                dashboard.update(now, rows, controller)

        traci.close()                                                 # SUMO finishes writing tripinfo here
        results = compute_results(tripinfo, queue_samples, controller.phase_switches)
        db.finish_run(run_id, results)
        finished = True
    finally:
        if traci.isLoaded():
            traci.close()
        if dashboard:
            dashboard.close()
        if not finished:
            db.finish_run(run_id, None)

    print_results(run_id, results, args.ambulances)
    print(f" Chart saved: {charts.run_chart(db, run_id)}")
    return {"run_id": run_id, "scheduler": scheduler, **results}


def compute_results(tripinfo: Path, queue_samples: list[int], phase_switches: int) -> dict:
    """Waiting time comes from SUMO's tripinfo file (completed trips); queues from the monitor."""
    trips = ET.parse(tripinfo).getroot().findall("tripinfo")
    waits = [float(t.get("waitingTime")) for t in trips]
    ambulance_delays = [float(t.get("timeLoss")) + float(t.get("departDelay"))
                        for t in trips if t.get("vType") == "ambulance"]
    return {
        "avg_wait_sec": round(sum(waits) / len(waits), 2) if waits else 0.0,
        "avg_queue": round(sum(queue_samples) / len(queue_samples), 2) if queue_samples else 0.0,
        "max_queue": max(queue_samples, default=0),
        "throughput": len(trips),
        "phase_switches": phase_switches,
        "ambulance_delay_sec": round(sum(ambulance_delays) / len(ambulance_delays), 2) if ambulance_delays else None,
    }


def print_results(run_id: int, r: dict, ambulances: bool) -> None:
    print(f"\n RESULTS (run {run_id})")
    print(f"   Average waiting time : {r['avg_wait_sec']:>7} s")
    print(f"   Average queue        : {r['avg_queue']:>7} vehicles per approach")
    print(f"   Maximum queue        : {r['max_queue']:>7} vehicles")
    print(f"   Vehicles completed   : {r['throughput']:>7}")
    print(f"   Phase switches       : {r['phase_switches']:>7}")
    if ambulances:
        print(f"   Ambulance delay      : {r['ambulance_delay_sec']:>7} s (average time lost per ambulance)")


def print_comparison(results: list[dict], ambulances: bool) -> None:
    best_wait = min(r["avg_wait_sec"] for r in results)
    print(f"\n{LINE}\n COMPARISON (same traffic, same seed)\n{LINE}")
    header = f" {'Scheduler':<16}{'Avg wait (s)':>13}{'Avg queue':>11}{'Max queue':>11}{'Completed':>11}{'Switches':>10}"
    print(header + (f"{'Ambulance delay':>17}" if ambulances else ""))
    for r in results:
        line = (f" {r['scheduler']:<16}{r['avg_wait_sec']:>13}{r['avg_queue']:>11}{r['max_queue']:>11}"
                f"{r['throughput']:>11}{r['phase_switches']:>10}")
        if ambulances:
            line += f"{str(r['ambulance_delay_sec']):>17}"
        print(line + ("   <- lowest wait" if r["avg_wait_sec"] == best_wait else ""))


def main() -> None:
    args = parse_args()
    db = Database()
    try:
        schedulers = list(ALGORITHMS) if args.scheduler == "all" else [args.scheduler]
        results = [run_simulation(args, s, db) for s in schedulers]
        if len(results) > 1:
            print_comparison(results, args.ambulances)
            path = charts.compare_chart(db, args.scenario, args.seed, args.duration, args.ambulances)
            print(f"\n Comparison chart saved: {path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
