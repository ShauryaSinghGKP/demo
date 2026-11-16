"""Signal controller: the only code that changes the traffic light in SUMO.

Safety rule: exactly one approach is ever green, and a green always ends with
3 s yellow + 1 s all-red before the next approach gets green. Nothing (not even an ambulance) skips that.

Life of one light:   GREEN --(time up)--> red light: all 5 algorithms vote --> YELLOW --> ALL-RED --> next GREEN
"""

import traci

from src.config import (
    ALL_RED_PHASE, ALL_RED_SECONDS, APPROACHES, EMERGENCY_GREEN, EMERGENCY_MAX_HOLD,
    EMERGENCY_MIN_GREEN_BEFORE_CUT, FIXED_GREEN, GREEN_PHASE, MIN_GREEN, TRAFFIC_LIGHT_ID, YELLOW_PHASE,
    YELLOW_SECONDS,
)
from src.schedulers import SHORT_NAME, vote_all

ARROW = {"north": "N", "east": "E", "south": "S", "west": "W", None: "-"}


class SignalController:
    def __init__(self, scheduler: str, run_id: int, db, verbose: bool = True):
        self.scheduler, self.run_id, self.db, self.verbose = scheduler, run_id, db, verbose
        self.approach, self.stage = "north", "green"          # start: North green
        self.green_started = 0
        self.target, self.next_green = None, 0                  # where we go after yellow + all-red
        self.last_served = {a: 0 for a in APPROACHES}
        self.phase_switches = 0
        self.last_votes, self.last_applied = {}, None           # shown by the live dashboard
        self.red_lights = 0
        self.hold_started = None                                # emergency: holding a green for an ambulance
        self.capped = set()                                     # approaches whose 60 s emergency hold ran out
        self._set_light(0, "green", FIXED_GREEN if scheduler == "fixed" else MIN_GREEN, "start: North green")

    # ------------------------------------------------------------------------------------------
    def step(self, now: int, state: dict) -> None:
        """Called once per simulated second with the latest MySQL state."""
        if self._handle_ambulance(now, state):
            return
        if now < self.deadline:
            return
        if self.stage == "green":
            self._red_light(now, state)
        elif self.stage == "yellow":
            self._set_light(now, "all_red", ALL_RED_SECONDS, "all-red clearance")
        else:
            self._enter_green(now)

    # ---- the red light: every algorithm votes, the selected one is applied ---------------------
    def _red_light(self, now: int, state: dict) -> None:
        self.last_served[self.approach] = now                # the green approach is being served right now
        votes = vote_all(state, self.approach, self.last_served, now)
        vote = votes[self.scheduler]
        self.last_votes, self.last_applied = votes, self.scheduler
        self.red_lights += 1
        if vote["approach"] is None:                         # nobody waiting: keep this green a bit longer
            self._extend_green(now, vote["green"])
            return
        self.db.save_decision(self.run_id, now, self.approach, vote["approach"], vote["green"],
                              self.scheduler, vote["why"], votes)
        self._print_decision(now, vote, votes, state)
        if vote["approach"] == self.approach:                # same approach again: extend, no yellow needed
            self._extend_green(now, vote["green"])
        else:
            self._start_switch(now, vote["approach"], vote["green"], f"switching to {vote['approach']}")

    # ---- emergency preemption (works like an OS interrupt) -------------------------------------
    def _handle_ambulance(self, now: int, state: dict) -> bool:
        """Returns True when an ambulance decided this second, so the normal scheduler waits."""
        calls = sorted((r["ambulance_distance_m"], a) for a, r in state.items() if r["ambulances"] > 0)
        self.capped &= {a for _, a in calls}                 # forget caps once that ambulance has gone
        calls = [a for _, a in calls if a not in self.capped]  # nearest ambulance first

        if not calls:
            if self.hold_started is not None:
                self.hold_started = None
                self.db.save_signal(self.run_id, now, self.approach, "green", "ambulance passed; normal scheduling")
            return False

        if self.stage == "green" and self.approach in calls:            # ambulance already has green: hold it
            if self.hold_started is None:
                self.hold_started = now
                self.db.save_signal(self.run_id, now, self.approach, "green", "holding green for ambulance")
                self._say(f" t={now:>3}s  AMBULANCE on {self.approach}: holding its green")
            if now - self.hold_started < EMERGENCY_MAX_HOLD:
                self._keep_green_until(max(self.deadline, now + 1), now)
                return True
            self.capped.add(self.approach)                    # 60 s cap reached: let the scheduler decide
            self.hold_started, self.deadline = None, now
            return False

        target = calls[0]
        if self.stage == "green":                            # another approach is green: cut it safely
            if now - self.green_started >= EMERGENCY_MIN_GREEN_BEFORE_CUT:
                reason = f"ambulance {state[target]['ambulance_distance_m']:.0f} m away on {target}"
                self.db.save_decision(self.run_id, now, self.approach, target, EMERGENCY_GREEN, "emergency",
                                      reason, None)
                self._say(f" t={now:>3}s  AMBULANCE on {target}: ending {self.approach} green early "
                          f"-> yellow -> all-red -> {target}")
                self._start_switch(now, target, EMERGENCY_GREEN, f"ambulance: ending green early for {target}")
            else:                                             # minimum 5 s green first
                self._keep_green_until(max(self.deadline, now + 1), now)
            return True

        if self.target != target:                            # in yellow/all-red: redirect the next green
            self.db.save_decision(self.run_id, now, self.approach, target, EMERGENCY_GREEN, "emergency",
                                  f"redirected next green to ambulance on {target}", None)
            self._say(f" t={now:>3}s  AMBULANCE on {target}: next green redirected to {target}")
            self.target, self.next_green = target, EMERGENCY_GREEN
        return False                                          # yellow/all-red timing continues unchanged

    # ---- light changes (the only place TraCI sets the signal) ---------------------------------
    def _start_switch(self, now: int, target: str, green: int, note: str) -> None:
        self.target, self.next_green, self.hold_started = target, green, None
        self.last_served[self.approach] = now
        self._set_light(now, "yellow", YELLOW_SECONDS, note)

    def _enter_green(self, now: int) -> None:
        if self.target != self.approach:
            self.phase_switches += 1
        self.approach, self.target = self.target, None
        self.green_started = now
        self.capped.discard(self.approach)
        self._set_light(now, "green", self.next_green, f"green for {self.next_green} s")
        self.db.ambulance_got_green(self.run_id, self.approach, now)

    def _set_light(self, now: int, stage: str, seconds: int, note: str) -> None:
        self.stage = stage
        phase = {"green": GREEN_PHASE, "yellow": YELLOW_PHASE, "all_red": ALL_RED_PHASE}[stage][self.approach]
        traci.trafficlight.setPhase(TRAFFIC_LIGHT_ID, phase)
        self._keep_green_until(now + seconds, now)
        self.db.save_signal(self.run_id, now, self.approach, stage, note)

    def _extend_green(self, now: int, seconds: int) -> None:
        self._keep_green_until(now + seconds, now)
        self.db.save_signal(self.run_id, now, self.approach, "green", f"green extended {seconds} s")

    def _keep_green_until(self, deadline: int, now: int) -> None:
        """Keep our deadline and SUMO's own phase timer in step, so SUMO never changes the light by itself."""
        self.deadline = deadline
        traci.trafficlight.setPhaseDuration(TRAFFIC_LIGHT_ID, max(1, deadline - now))

    # ---- terminal output -----------------------------------------------------------------------
    def _say(self, text: str) -> None:
        if self.verbose:
            print(text)

    def _print_decision(self, now: int, vote: dict, votes: dict, state: dict) -> None:
        picks = "  ".join(f"{SHORT_NAME[n]}:{ARROW[v['approach']]}{'*' if n == self.scheduler else ''}"
                          for n, v in votes.items())
        queues = " ".join(f"{ARROW[a]}{state[a]['queue']}" for a in APPROACHES)
        self._say(f" t={now:>3}s  {ARROW[self.approach]}->{ARROW[vote['approach']]}  green {vote['green']:>2}s"
                  f"  | votes {picks}  | queues {queues}")


class AmbulanceTracker:
    """Records each ambulance in MySQL: when it was detected, got green, and crossed the stop line."""

    def __init__(self, run_id: int, db):
        self.run_id, self.db, self.on_road = run_id, db, {}

    def update(self, now: int, rows: list[dict], green_approach: str | None) -> None:
        seen = set()
        for row in rows:
            for vehicle in row["ambulance_ids"]:
                seen.add(vehicle)
                if vehicle not in self.on_road:
                    self.on_road[vehicle] = row["approach"]
                    self.db.ambulance_detected(self.run_id, vehicle, row["approach"], now,
                                               green_approach == row["approach"])
        for vehicle in set(self.on_road) - seen:            # left the approach road = crossed the junction
            self.db.ambulance_crossed(self.run_id, vehicle, now)
            del self.on_road[vehicle]
