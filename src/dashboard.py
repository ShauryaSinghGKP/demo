"""Live matplotlib window shown while the simulation runs (disable with --no-live)."""

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import APPROACHES, DASHBOARD_REFRESH_SECONDS  # noqa: E402
from src.schedulers import ALGORITHMS, SHORT_NAME  # noqa: E402

APPROACH_COLOR = {"north": "#2a78d6", "east": "#eb6834", "south": "#1baf7a", "west": "#eda100"}
LIGHT_COLOR = {"green": "#1baf7a", "yellow": "#eda100", "red": "#e34948"}
POSITION = {"north": (0, 1), "east": (1, 0), "south": (0, -1), "west": (-1, 0)}
INK, MUTED, GRID = "#0b0b0b", "#8a8984", "#e4e3df"


class LiveDashboard:
    def __init__(self, title: str):
        plt.ion()
        self.fig = plt.figure(figsize=(12, 7))
        self.fig.canvas.manager.set_window_title("Adaptive Traffic Signal - live")
        self.fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
        grid = self.fig.add_gridspec(2, 3, width_ratios=[2.2, 1, 1.2], hspace=0.45, wspace=0.35)
        self.ax_queue = self.fig.add_subplot(grid[0, :2])
        self.ax_junction = self.fig.add_subplot(grid[0, 2])
        self.ax_votes = self.fig.add_subplot(grid[1, :2])
        self.ax_agree = self.fig.add_subplot(grid[1, 2])
        self.times, self.queues = [], {a: [] for a in APPROACHES}
        self.agree = {name: 0 for name in ALGORITHMS}
        self.red_lights = 0
        self.open = True
        self.fig.canvas.mpl_connect("close_event", lambda _event: setattr(self, "open", False))

    def update(self, now: int, rows: list[dict], controller) -> None:
        self.times.append(now)
        for row in rows:
            self.queues[row["approach"]].append(row["queue"])
        if controller.red_lights > self.red_lights:            # a new red light happened since last update
            applied = controller.last_votes[controller.last_applied]["approach"]
            self.red_lights += 1
            for name, vote in controller.last_votes.items():
                self.agree[name] += vote["approach"] == applied
        if self.open and now % DASHBOARD_REFRESH_SECONDS == 0:
            self._draw(now, rows, controller)

    def _draw(self, now: int, rows: list[dict], controller) -> None:
        by_approach = {r["approach"]: r for r in rows}

        ax = self.ax_queue                                    # queue length over time
        ax.clear()
        for a in APPROACHES:
            ax.plot(self.times, self.queues[a], color=APPROACH_COLOR[a], linewidth=1.8, label=a.title())
        ax.set_title("Halted vehicles per approach", loc="left", fontsize=10)
        ax.set_xlabel("Simulation time (s)")
        ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=8)
        ax.grid(color=GRID)
        ax.spines[["top", "right"]].set_visible(False)

        ax = self.ax_junction                                 # the intersection right now
        ax.clear()
        ax.set_xlim(-1.8, 1.8), ax.set_ylim(-1.8, 1.8), ax.set_aspect("equal"), ax.axis("off")
        ax.add_patch(plt.Rectangle((-0.25, -1.6), 0.5, 3.2, color=GRID))
        ax.add_patch(plt.Rectangle((-1.6, -0.25), 3.2, 0.5, color=GRID))
        for a in APPROACHES:
            color = "red"
            if a == controller.approach and controller.stage in ("green", "yellow"):
                color = controller.stage
            x, y = POSITION[a]
            ax.add_patch(plt.Circle((x * 0.62, y * 0.62), 0.17, color=LIGHT_COLOR[color]))
            label = f"{a[0].upper()}  q={by_approach[a]['queue']}"
            if by_approach[a]["ambulances"]:
                label += "\nAMBULANCE"
            ax.text(x * 1.35, y * 1.35, label, ha="center", va="center", fontsize=8,
                    color="#e34948" if by_approach[a]["ambulances"] else INK, fontweight="bold")
        ax.set_title(f"t = {now} s   ({controller.stage.replace('_', '-')})", fontsize=10)

        ax = self.ax_votes                                    # what every algorithm voted at the last red light
        ax.clear()
        ax.axis("off")
        ax.set_title("Last red light: every algorithm's choice (highlighted = applied)", loc="left", fontsize=10)
        for i, (name, vote) in enumerate(controller.last_votes.items()):
            applied = name == controller.last_applied
            y = 0.85 - i * 0.19
            ax.text(0.0, y, SHORT_NAME[name], fontsize=10, fontweight="bold" if applied else "normal",
                    transform=ax.transAxes)
            choice = (vote["approach"] or "none").title()
            ax.text(0.14, y, f"-> {choice:<6} {vote['green']:>2}s", fontsize=10, family="monospace",
                    fontweight="bold" if applied else "normal", transform=ax.transAxes,
                    bbox={"facecolor": "#cde2fb", "edgecolor": "none"} if applied else None)
            ax.text(0.38, y, vote["why"][:60], fontsize=8.5, color=MUTED, transform=ax.transAxes)

        ax = self.ax_agree                                    # how often each algorithm agreed with the applied one
        ax.clear()
        names = list(ALGORITHMS)
        values = [100 * self.agree[n] / self.red_lights if self.red_lights else 0 for n in names]
        ax.barh([SHORT_NAME[n] for n in names], values, color="#2a78d6", height=0.6)
        ax.invert_yaxis()
        ax.set_xlim(0, 120)
        ax.set_title(f"Agreed with applied choice\n({self.red_lights} red lights)", fontsize=10)
        ax.set_xlabel("%")
        ax.spines[["top", "right"]].set_visible(False)
        for y, value in enumerate(values):
            ax.text(value + 2, y, f"{value:.0f}%", va="center", fontsize=8)

        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        plt.pause(0.001)

    def close(self) -> None:
        plt.ioff()
        plt.close(self.fig)
