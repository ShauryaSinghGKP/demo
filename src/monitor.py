"""Traffic monitor: every simulated second, read what is waiting on each approach from SUMO (via TraCI)."""

import traci

from src.config import APPROACH_LANE, APPROACHES

VEHICLE_KIND = {"passenger": "cars", "truck": "trucks", "motorcycle": "bikes", "emergency": "ambulances"}


class TrafficMonitor:
    def __init__(self):
        self.queue_started = {a: None for a in APPROACHES}   # when each approach's current queue began
        self.kind_cache = {}                                  # vehicle id -> kind (never changes)

    def read(self, now: int) -> list[dict]:
        """Return one dict per approach: vehicles, queue, oldest wait, vehicle classes, nearest ambulance."""
        rows = []
        for approach in APPROACHES:
            lane = APPROACH_LANE[approach]
            lane_length = traci.lane.getLength(lane)
            row = {"approach": approach, "vehicles": 0, "cars": 0, "trucks": 0, "bikes": 0,
                   "ambulances": 0, "ambulance_distance_m": None, "ambulance_ids": []}

            for vehicle in traci.lane.getLastStepVehicleIDs(lane):
                if vehicle not in self.kind_cache:
                    self.kind_cache[vehicle] = VEHICLE_KIND.get(traci.vehicle.getVehicleClass(vehicle), "cars")
                kind = self.kind_cache[vehicle]
                row[kind] += 1
                row["vehicles"] += 1
                if kind == "ambulances":
                    distance = round(lane_length - traci.vehicle.getLanePosition(vehicle), 1)
                    row["ambulance_ids"].append(vehicle)
                    if row["ambulance_distance_m"] is None or distance < row["ambulance_distance_m"]:
                        row["ambulance_distance_m"] = distance

            row["queue"] = traci.lane.getLastStepHaltingNumber(lane)
            if row["queue"] == 0:
                self.queue_started[approach] = None
            elif self.queue_started[approach] is None:
                self.queue_started[approach] = now
            row["oldest_wait_sec"] = 0 if self.queue_started[approach] is None else now - self.queue_started[approach]
            rows.append(row)
        return rows
