"""
router.py
---------
Router model for the SA-RIP vs RIP simulation.

Modes:
  - RIP     : classic distance-vector routing using hop count
  - SA-RIP  : adaptive metric + backup route cache + sequence validation

SA-RIP metric:
    Metric = alpha * H + beta * D + gamma * C

where:
    H = hop count
    D = link delay
    C = congestion/capacity-related cost
"""

from dataclasses import dataclass
from typing import Dict


INFINITY_RIP = 16
INFINITY_SARIP = 256

# ---------------- SA-RIP WEIGHTING CONSTANTS ----------------
# You can tune these values depending on what you want to prioritize.
ALPHA = 1.0    # hop-count weight
BETA = 0.1     # delay weight
GAMMA = 0.5    # congestion/capacity weight


@dataclass
class RouteEntry:
    """One routing table entry."""
    next_hop: str
    metric: int
    seq_num: int = 0


class Router:
    """A single router participating in RIP or SA-RIP."""

    def __init__(self, name: str, graph, mode: str = "RIP"):
        assert mode in ("RIP", "SA-RIP"), f"Unknown mode: {mode}"

        self.name = name
        self.graph = graph
        self.mode = mode

        self.routing_table: Dict[str, RouteEntry] = {}
        self.backup_table: Dict[str, RouteEntry] = {}

        self.my_seq_num = 0
        self.last_seen_seq: Dict[str, int] = {}

        self.dirty = False

        self.routing_table[self.name] = RouteEntry(
            next_hop=self.name,
            metric=0,
            seq_num=0
        )

    # ------------------------------------------------------------------

    def neighbors(self):
        """Return currently connected neighbors."""
        return list(self.graph.neighbors(self.name))

    def infinity(self) -> int:
        """Return protocol-specific infinity value."""
        return INFINITY_RIP if self.mode == "RIP" else INFINITY_SARIP

    def link_cost(self, neighbor: str) -> int:
        """
        Return cost of the direct link to a neighbor.

        RIP:
            cost = 1 hop

        SA-RIP:
            cost = alpha * hop + beta * delay + gamma * congestion_cost
        """
        if not self.graph.has_edge(self.name, neighbor):
            return self.infinity()

        if self.mode == "RIP":
            return 1

        # SA-RIP adaptive metric
        hop_cost = 1
        delay = self.graph[self.name][neighbor]["delay"]
        capacity = self.graph[self.name][neighbor]["capacity"]

        # Lower capacity means higher congestion-related cost.
        # Example:
        # capacity = 100 Mbps -> cost = 1
        # capacity = 10 Mbps  -> cost = 10
        congestion_cost = 100 / capacity

        metric = (
            ALPHA * hop_cost
            + BETA * delay
            + GAMMA * congestion_cost
        )

        return max(1, int(round(metric)))

    # ------------------------------------------------------------------

    def copy_entry(self, entry: RouteEntry) -> RouteEntry:
        """Return a safe copy of a route entry."""
        return RouteEntry(
            next_hop=entry.next_hop,
            metric=entry.metric,
            seq_num=entry.seq_num
        )

    # ------------------------------------------------------------------

    def build_full_update(self):
        """Build a full routing-table update."""
        return [
            (dest, entry.metric)
            for dest, entry in self.routing_table.items()
        ]

    def build_changed_update(self, changed_destinations):
        """Build a partial update containing only changed routes."""
        return [
            (dest, self.routing_table[dest].metric)
            for dest in changed_destinations
            if dest in self.routing_table
        ]

    def apply_split_horizon(self, update, recipient):
        """
        Do not advertise a route back to the neighbor from which it was learned.
        """
        filtered = []

        for dest, metric in update:
            entry = self.routing_table.get(dest)

            if entry and entry.next_hop == recipient and dest != self.name:
                continue

            filtered.append((dest, metric))

        return filtered

    # ------------------------------------------------------------------

    def receive_update(self, sender: str, update, seq_num: int = 0):
        """
        Process routing update from a neighbor.

        Returns:
            set of destinations whose routes changed
        """

        # SA-RIP rejects stale/replayed updates.
        if self.mode == "SA-RIP":
            last_seen = self.last_seen_seq.get(sender, -1)

            if seq_num <= last_seen:
                return set()

            self.last_seen_seq[sender] = seq_num

        link = self.link_cost(sender)
        changed = set()

        for dest, advertised_metric in update:

            if dest == self.name:
                continue

            new_metric = advertised_metric + link

            if new_metric > self.infinity():
                new_metric = self.infinity()

            current = self.routing_table.get(dest)

            # CASE 1: No route exists
            if current is None:
                if new_metric < self.infinity():
                    self.routing_table[dest] = RouteEntry(
                        next_hop=sender,
                        metric=new_metric,
                        seq_num=seq_num
                    )
                    changed.add(dest)

            # CASE 2: Update from current next-hop
            elif current.next_hop == sender:

                if new_metric != current.metric:

                    if (
                        self.mode == "SA-RIP"
                        and new_metric >= self.infinity()
                        and dest in self.backup_table
                    ):
                        backup = self.backup_table.pop(dest)

                        if self.graph.has_edge(self.name, backup.next_hop):
                            self.routing_table[dest] = backup
                        else:
                            current.metric = self.infinity()
                            current.seq_num = seq_num

                    else:
                        current.metric = new_metric
                        current.seq_num = seq_num

                    changed.add(dest)

            # CASE 3: Alternative route from another neighbor
            else:

                if new_metric < current.metric:

                    if self.mode == "SA-RIP":
                        self.backup_table[dest] = self.copy_entry(current)

                    self.routing_table[dest] = RouteEntry(
                        next_hop=sender,
                        metric=new_metric,
                        seq_num=seq_num
                    )

                    changed.add(dest)

                elif self.mode == "SA-RIP" and new_metric < self.infinity():

                    backup = self.backup_table.get(dest)

                    if backup is None or new_metric < backup.metric:
                        self.backup_table[dest] = RouteEntry(
                            next_hop=sender,
                            metric=new_metric,
                            seq_num=seq_num
                        )

        if changed:
            self.dirty = True

        return changed

    # ------------------------------------------------------------------

    def handle_link_failure(self, dead_neighbor: str):
        """
        Called when a direct link fails.

        Returns:
            set of destinations affected by the failure
        """
        affected = set()

        for dest, entry in list(self.routing_table.items()):

            if dest == self.name:
                continue

            if entry.next_hop == dead_neighbor:

                if self.mode == "SA-RIP" and dest in self.backup_table:
                    backup = self.backup_table.pop(dest)

                    if (
                        backup.next_hop != dead_neighbor
                        and self.graph.has_edge(self.name, backup.next_hop)
                    ):
                        self.routing_table[dest] = backup
                        affected.add(dest)
                        continue

                entry.metric = self.infinity()
                affected.add(dest)

        # Remove invalid backup routes using the failed neighbor.
        if self.mode == "SA-RIP":
            for dest, backup in list(self.backup_table.items()):
                if backup.next_hop == dead_neighbor:
                    del self.backup_table[dest]

        if affected:
            self.dirty = True

        return affected

    # ------------------------------------------------------------------

    def known_destinations(self):
        """Return reachable destinations."""
        return {
            dest
            for dest, entry in self.routing_table.items()
            if entry.metric < self.infinity()
        }

    def __repr__(self):
        return f"Router({self.name}, {self.mode})"


# ----------------------------------------------------------------------
if __name__ == "__main__":
    from network import build_topology_8

    g = build_topology_8()

    r0 = Router("R0", g, mode="RIP")
    r1 = Router("R1", g, mode="RIP")

    print(f"Created: {r0}, {r1}")
    print(f"R0's neighbors: {r0.neighbors()}")
    print(f"R0's link cost to R1: {r0.link_cost('R1')}")
    print(f"R0's initial routing table: {r0.routing_table}")

    update = r1.build_full_update()
    changed = r0.receive_update("R1", update, seq_num=1)

    print(f"\nAfter receiving R1's update, R0 changed routes for: {changed}")
    print("R0's table now:")

    for dest, entry in r0.routing_table.items():
        print(f"  {dest}: via {entry.next_hop}, metric {entry.metric}")