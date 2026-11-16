"""Every tunable number in one place. These are simulation parameters, not real-world signal timings."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- SUMO files ---------------------------------------------------------------------------
NETWORK_FILE = ROOT / "simulation/network/intersection.net.xml"
SCENARIOS = {
    "light": ROOT / "simulation/routes/light.rou.xml",          # 6 vehicles, quick demo
    "moderate": ROOT / "simulation/routes/moderate.rou.xml",    # busy but below capacity
    "peak": ROOT / "simulation/routes/peak.rou.xml",            # light -> rush hour -> moderate
    "asymmetric": ROOT / "simulation/routes/asymmetric.rou.xml",  # north much busier (overloaded)
    "heavy": ROOT / "simulation/routes/heavy.rou.xml",          # every approach overloaded
}
AMBULANCE_ROUTE_FILE = ROOT / "simulation/routes/emergency.rou.xml"
TRAFFIC_LIGHT_ID = "center"
DEFAULT_DURATION = 400       # simulated seconds
GUI_DELAY_MS = 300           # SUMO-GUI pause per step so the signal changes are visible

# ---- Intersection layout ------------------------------------------------------------------
# Order matters: Fixed-time and Round Robin rotate North -> East -> South -> West.
APPROACHES = ("north", "east", "south", "west")
APPROACH_LANE = {"north": "north_in_0", "east": "east_in_0", "south": "south_in_0", "west": "west_in_0"}
# Phase indices in simulation/network/intersection.tll.xml (green, yellow, all-red per approach)
GREEN_PHASE = {"north": 0, "east": 3, "south": 6, "west": 9}
YELLOW_PHASE = {a: p + 1 for a, p in GREEN_PHASE.items()}
ALL_RED_PHASE = {a: p + 2 for a, p in GREEN_PHASE.items()}

# ---- Signal timing (safety) ---------------------------------------------------------------
YELLOW_SECONDS = 3
ALL_RED_SECONDS = 1
MIN_GREEN = 10
MAX_GREEN = 30

# ---- Scheduler parameters -----------------------------------------------------------------
FIXED_GREEN = 30                 # Fixed-time baseline
RR_QUANTUM = 20                  # Round Robin time slice
GREEN_BASE = 10                  # adaptive green = 10 s + 2 s per queued vehicle (10-30 s)
GREEN_PER_VEHICLE = 2
TYPE_WEIGHT = {"truck": 3, "car": 2, "bike": 1}   # Priority + Aging demand weights
AGING_PER_SECOND = 1.0           # Priority + Aging: +1 point for every second an approach waits

# Hybrid: picks one of the algorithms above from the live traffic state
HYBRID_STARVATION_SECONDS = 120  # > one full overloaded cycle of the other 3 approaches (3 x 34 s)
HYBRID_LIGHT_QUEUE = 6           # total halted vehicles <= 6  -> light traffic -> FCFS
HYBRID_IMBALANCE = 1.5           # busiest queue >= 1.5 x average -> imbalanced -> Priority + Aging

# ---- Emergency vehicles -------------------------------------------------------------------
EMERGENCY_MIN_GREEN_BEFORE_CUT = 5   # a running green is shown at least 5 s before an ambulance cuts it
EMERGENCY_GREEN = 10                 # green given to the ambulance approach (then held while it is there)
EMERGENCY_MAX_HOLD = 60              # never hold one approach green for more than 60 s

# ---- Live dashboard -----------------------------------------------------------------------
DASHBOARD_REFRESH_SECONDS = 2        # redraw the live matplotlib window every 2 simulated seconds
OUTPUT_DIR = ROOT / "outputs"
