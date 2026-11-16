"""Saved matplotlib charts, drawn from MySQL after a run.

    python -m src.charts --run 12                          one run in detail
    python -m src.charts --compare moderate --seed 42      latest run of each scheduler, side by side
"""

import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from src.config import APPROACHES, OUTPUT_DIR
from src.database import Database
from src.schedulers import ALGORITHMS

NAME = {"fixed": "Fixed", "fcfs": "FCFS", "round_robin": "Round Robin", "priority_aging": "Priority+Aging",
        "hybrid": "Hybrid"}
SCHEDULER_COLOR = {"fixed": "#2a78d6", "fcfs": "#eb6834", "round_robin": "#1baf7a",
                   "priority_aging": "#eda100", "hybrid": "#e87ba4"}
APPROACH_COLOR = {"north": "#2a78d6", "east": "#eb6834", "south": "#1baf7a", "west": "#eda100"}
INK, MUTED, GRID, SURFACE, RED = "#0b0b0b", "#6f6e69", "#e4e3df", "#fcfcfb", "#e34948"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "font.size": 9,
    "axes.edgecolor": GRID, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": MUTED,
})


def _save(fig, name: str) -> str:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return str(path.relative_to(OUTPUT_DIR.parent))


def run_chart(db: Database, run_id: int) -> str:
    """Queues over time, the signal timeline with ambulances, algorithm agreement, and the key results."""
    run = db.query("SELECT * FROM runs WHERE run_id=%s", (run_id,))[0]
    snaps = db.query("SELECT sim_time, approach, queue FROM traffic_snapshots WHERE run_id=%s ORDER BY sim_time",
                     (run_id,))
    events = db.query("SELECT sim_time, approach, state FROM signal_events WHERE run_id=%s ORDER BY event_id",
                      (run_id,))
    ambulances = db.query("SELECT * FROM ambulances WHERE run_id=%s", (run_id,))
    agreement = db.query("""SELECT v.algorithm, AVG(v.chosen_approach <=> d.to_approach) * 100 AS pct
                            FROM votes v JOIN decisions d USING (decision_id)
                            WHERE d.run_id=%s GROUP BY v.algorithm""", (run_id,))
    end = run["duration_sec"]

    fig = plt.figure(figsize=(12, 8))
    grid = fig.add_gridspec(3, 2, height_ratios=[2.2, 1.3, 1.6], hspace=0.55, wspace=0.25)
    fig.suptitle(f"Run {run_id}: {run['scenario']} traffic, {NAME[run['scheduler']]} in control, seed {run['seed']}"
                 + ("  (with ambulances)" if run["ambulances_on"] else ""), x=0.01, ha="left",
                 fontsize=12, fontweight="bold")

    ax = fig.add_subplot(grid[0, :])                          # 1. queues over time
    for a in APPROACHES:
        points = [(s["sim_time"], s["queue"]) for s in snaps if s["approach"] == a]
        ax.plot([p[0] for p in points], [p[1] for p in points], color=APPROACH_COLOR[a], lw=1.6, label=a.title())
    for amb in ambulances:
        ax.axvline(amb["detected_at"], color=RED, lw=0.8, ls=":")
    ax.set_title("Halted vehicles per approach" + ("  (dotted red line = ambulance detected)" if ambulances else ""))
    ax.set_xlim(0, end)
    ax.set_ylabel("vehicles")
    ax.legend(ncol=4, loc="upper right")

    ax = fig.add_subplot(grid[1, :])                          # 2. which approach had the light
    row = {a: i for i, a in enumerate(APPROACHES)}
    for i, event in enumerate(events):
        stop = events[i + 1]["sim_time"] if i + 1 < len(events) else end
        if event["state"] in ("green", "yellow") and stop > event["sim_time"]:
            ax.broken_barh([(event["sim_time"], stop - event["sim_time"])], (row[event["approach"]] - 0.35, 0.7),
                           color="#1baf7a" if event["state"] == "green" else "#eda100")
    for amb in ambulances:
        crossed = amb["crossed_at"] or end
        ax.plot([amb["detected_at"], crossed], [row[amb["approach"]]] * 2, color=INK, lw=1.4)
        ax.plot(amb["detected_at"], row[amb["approach"]], "o", color=RED, ms=6, mec=SURFACE)
    ax.set_yticks(range(4), [a.title() for a in APPROACHES])
    ax.invert_yaxis()
    ax.set_xlim(0, end)
    ax.set_xlabel("Simulation time (s)")
    ax.grid(axis="y", visible=False)
    legend = [Patch(color="#1baf7a", label="green"), Patch(color="#eda100", label="yellow")]
    if ambulances:
        legend.append(plt.Line2D([], [], color=INK, marker="o", mfc=RED, mec=SURFACE, label="ambulance waiting"))
    ax.legend(handles=legend, ncol=3, loc="lower right", bbox_to_anchor=(1, 1))
    ax.set_title("Signal timeline")

    ax = fig.add_subplot(grid[2, 0])                          # 3. agreement between algorithms
    pct = {r["algorithm"]: float(r["pct"]) for r in agreement}
    names = [n for n in ALGORITHMS if n in pct]
    ax.barh([NAME[n] for n in names], [pct[n] for n in names], height=0.6,
            color=[SCHEDULER_COLOR[n] for n in names])
    for y, n in enumerate(names):
        ax.text(pct[n] + 1.5, y, f"{pct[n]:.0f}%", va="center", fontsize=8, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 110)
    ax.set_title("At each red light, how often each algorithm\nchose the same approach that was applied")
    ax.grid(axis="y", visible=False)

    ax = fig.add_subplot(grid[2, 1])                          # 4. key results
    ax.axis("off")
    ax.set_title("Results")
    tiles = [("Average wait", f"{run['avg_wait_sec']} s"), ("Average queue", f"{run['avg_queue']}"),
             ("Max queue", f"{run['max_queue']}"), ("Vehicles completed", f"{run['throughput']}"),
             ("Phase switches", f"{run['phase_switches']}")]
    if run["ambulances_on"]:
        tiles.append(("Ambulance delay", f"{run['ambulance_delay_sec']} s"))
    for i, (label, value) in enumerate(tiles):
        x, y = (i % 3) / 3, 0.62 - (i // 3) * 0.55
        ax.text(x, y + 0.2, label, fontsize=8.5, color=MUTED, transform=ax.transAxes)
        ax.text(x, y, value, fontsize=16, fontweight="bold", color=INK, transform=ax.transAxes)
    return _save(fig, f"run_{run_id}.png")


def compare_chart(db: Database, scenario: str, seed: int, duration: int, ambulances: bool) -> str:
    """Latest completed run of every scheduler for the same scenario/seed/duration, one panel per metric."""
    runs = db.query("""SELECT r.* FROM runs r JOIN (
                           SELECT scheduler, MAX(run_id) AS run_id FROM runs
                           WHERE status='completed' AND scenario=%s AND seed=%s AND duration_sec=%s
                             AND ambulances_on=%s GROUP BY scheduler) latest USING (run_id)""",
                    (scenario, seed, duration, ambulances))
    runs = sorted(runs, key=lambda r: list(ALGORITHMS).index(r["scheduler"]))
    if not runs:
        raise ValueError("No completed runs to compare for these settings")
    metrics = [("avg_wait_sec", "Average waiting time (s)", "lower is better"),
               ("avg_queue", "Average queue (vehicles)", "lower is better"),
               ("max_queue", "Maximum queue (vehicles)", "lower is better"),
               ("throughput", "Vehicles completed", "higher is better"),
               ("phase_switches", "Phase switches", "fewer = less time lost to yellow/all-red")]
    if ambulances:
        metrics.append(("ambulance_delay_sec", "Ambulance delay (s)", "lower is better"))
    cols = 3
    fig, axes = plt.subplots(2, cols, figsize=(12, 6.5))
    fig.suptitle(f"Scheduler comparison: {scenario} traffic, seed {seed}, {duration} s"
                 + (", with ambulances" if ambulances else ""), x=0.01, ha="left", fontsize=12, fontweight="bold")
    for ax, (column, title, hint) in zip(axes.flat, metrics):
        values = [float(r[column] or 0) for r in runs]
        best = (max if column == "throughput" else min)(values)
        ax.bar([NAME[r["scheduler"]].replace("+", "+\n").replace(" ", "\n") for r in runs], values,
               color=[SCHEDULER_COLOR[r["scheduler"]] for r in runs], width=0.7, edgecolor=SURFACE, lw=2)
        for x, value in enumerate(values):
            ax.text(x, value, f"{value:g}", ha="center", va="bottom", fontsize=8,
                    fontweight="bold" if value == best else "normal", color=INK)
        ax.set_title(title, fontsize=10, pad=16)
        ax.text(0, 1.02, hint, transform=ax.transAxes, fontsize=7.5, color=MUTED, va="bottom")
        ax.grid(axis="x", visible=False)
        ax.tick_params(axis="x", labelsize=7.5)
    for ax in list(axes.flat)[len(metrics):]:
        ax.axis("off")
    fig.text(0.01, -0.01, "Bold value = best. One run per scheduler with the same traffic and seed.",
             fontsize=8, color=MUTED)
    fig.tight_layout()
    tag = "_ambulances" if ambulances else ""
    return _save(fig, f"compare_{scenario}_seed{seed}{tag}.png")


if __name__ == "__main__":
    plt.switch_backend("Agg")      # files only, no window
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=int, help="run_id to chart")
    parser.add_argument("--compare", metavar="SCENARIO", help="compare schedulers for this scenario")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--duration", type=int, default=400)
    parser.add_argument("--ambulances", action="store_true")
    args = parser.parse_args()
    database = Database()
    if args.run:
        print("saved", run_chart(database, args.run))
    if args.compare:
        print("saved", compare_chart(database, args.compare, args.seed, args.duration, args.ambulances))
    database.close()
