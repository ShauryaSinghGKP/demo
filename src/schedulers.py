"""The five scheduling algorithms (OS CPU-scheduling ideas applied to a traffic light).

Every algorithm gets the SAME input, read from MySQL at the red light:
    state        {approach: latest traffic_snapshots row}  (queue, vehicles, oldest_wait_sec, cars, ...)
    current      the approach whose green is ending
    last_served  {approach: sim time its last green ended}
    now          current simulation second
and returns a vote:  {"approach": next green (None = no traffic), "green": seconds, "score": number, "why": text}

At every red light ALL five vote (so they can be compared live); the one chosen on the command line is applied.
"""

from src.config import (
    AGING_PER_SECOND, APPROACHES, FIXED_GREEN, GREEN_BASE, GREEN_PER_VEHICLE, HYBRID_IMBALANCE,
    HYBRID_LIGHT_QUEUE, HYBRID_STARVATION_SECONDS, MAX_GREEN, MIN_GREEN, RR_QUANTUM, TYPE_WEIGHT,
)


def adaptive_green(queue: int) -> int:
    """10 s + 2 s per halted vehicle, kept between 10 and 30 s."""
    return max(MIN_GREEN, min(MAX_GREEN, GREEN_BASE + GREEN_PER_VEHICLE * queue))


def waiting_approaches(state: dict) -> list[str]:
    return [a for a in APPROACHES if state[a]["vehicles"] > 0]


def next_in_cycle(current: str, candidates: list[str]) -> str:
    """First candidate after `current` in the fixed order North -> East -> South -> West."""
    start = APPROACHES.index(current)
    for step in range(1, len(APPROACHES) + 1):
        approach = APPROACHES[(start + step) % len(APPROACHES)]
        if approach in candidates:
            return approach
    return current


def no_traffic(why: str = "no vehicles waiting") -> dict:
    return {"approach": None, "green": MIN_GREEN, "score": 0, "why": why}


# ---- 1. Fixed-time: blind rotation, like a classic timer signal -----------------------------
def fixed(state, current, last_served, now):
    return {"approach": next_in_cycle(current, list(APPROACHES)), "green": FIXED_GREEN, "score": 0,
            "why": "fixed 30 s rotation"}


# ---- 2. FCFS: serve the queue that formed first -------------------------------------------
def fcfs(state, current, last_served, now):
    waiting = waiting_approaches(state)
    if not waiting:
        return no_traffic()
    pick = max(waiting, key=lambda a: state[a]["oldest_wait_sec"])
    return {"approach": pick, "green": adaptive_green(state[pick]["queue"]),
            "score": state[pick]["oldest_wait_sec"], "why": f"oldest queue ({state[pick]['oldest_wait_sec']} s)"}


# ---- 3. Round Robin: next non-empty approach, fixed time slice (quantum) ---------------------
def round_robin(state, current, last_served, now):
    waiting = waiting_approaches(state)
    if not waiting:
        return no_traffic()
    pick = next_in_cycle(current, waiting)
    return {"approach": pick, "green": RR_QUANTUM, "score": state[pick]["queue"],
            "why": f"next in turn, {RR_QUANTUM} s quantum"}


# ---- 4. Priority + Aging: heavier vehicles and longer waits raise priority -------------------
def priority_score(row: dict, last_served: dict, now: int) -> float:
    demand = (TYPE_WEIGHT["truck"] * row["trucks"] + TYPE_WEIGHT["car"] * row["cars"]
              + TYPE_WEIGHT["bike"] * row["bikes"] + row["queue"])
    waited = max(now - last_served[row["approach"]], row["oldest_wait_sec"])   # aging prevents starvation
    return demand + AGING_PER_SECOND * waited


def priority_aging(state, current, last_served, now):
    waiting = waiting_approaches(state)
    if not waiting:
        return no_traffic()
    pick = max(waiting, key=lambda a: priority_score(state[a], last_served, now))
    score = priority_score(state[pick], last_served, now)
    return {"approach": pick, "green": adaptive_green(state[pick]["queue"]), "score": round(score, 1),
            "why": f"highest priority score {score:.0f}"}


# ---- 5. Hybrid: look at the traffic, then use the algorithm that suits it -------------------
def hybrid(state, current, last_served, now):
    waiting = waiting_approaches(state)
    if not waiting:
        return no_traffic()

    # Rule 1 - starvation guard: anyone unserved for too long goes first.
    starving = [a for a in waiting if a != current and now - last_served[a] >= HYBRID_STARVATION_SECONDS]
    if starving:
        pick = max(starving, key=lambda a: now - last_served[a])
        return {"approach": pick, "green": adaptive_green(state[pick]["queue"]),
                "score": now - last_served[pick], "mode": "starvation guard",
                "why": f"starvation guard: {pick} unserved {now - last_served[pick]} s"}

    queues = [state[a]["queue"] for a in waiting]
    total, busiest, average = sum(queues), max(queues), sum(queues) / len(queues)
    if total <= HYBRID_LIGHT_QUEUE:                          # Rule 2 - light traffic
        mode, vote = "light -> FCFS", fcfs(state, current, last_served, now)
    elif busiest >= HYBRID_IMBALANCE * average:              # Rule 3 - one approach much busier
        mode, vote = "imbalanced -> Priority+Aging", priority_aging(state, current, last_served, now)
    else:                                                    # Rule 4 - evenly busy
        mode, vote = "balanced -> Round Robin", round_robin(state, current, last_served, now)
        vote["green"] = adaptive_green(state[vote["approach"]]["queue"])   # slice sized to the queue
    return {**vote, "mode": mode, "why": f"{mode}: {vote['why']}"}


ALGORITHMS = {"fixed": fixed, "fcfs": fcfs, "round_robin": round_robin,
              "priority_aging": priority_aging, "hybrid": hybrid}
SHORT_NAME = {"fixed": "Fixed", "fcfs": "FCFS", "round_robin": "RR", "priority_aging": "P+A", "hybrid": "Hybrid"}


def vote_all(state: dict, current: str, last_served: dict, now: int) -> dict[str, dict]:
    """Ask every algorithm what it would do right now."""
    return {name: algorithm(state, current, last_served, now) for name, algorithm in ALGORITHMS.items()}
