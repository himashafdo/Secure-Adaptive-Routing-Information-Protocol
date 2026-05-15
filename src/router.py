"""
router.py
---------
Router model for the SA-RIP vs RIP simulation.

Each Router maintains:
  - A routing table mapping destination -> (next_hop, metric)
  - A backup route cache (for SA-RIP only which we implemented)
  - A sequence number table tracking the latest seq # seen from each neighbor
  - A reference to the network graph so it knows its neighbors

Two protocol modes are supported via the `mode` field:
  - "RIP"    : classic distance-vector with periodic full-table updates
  - "SA-RIP" : triggered selective updates + backup route cache + seq numbers

The Simulator (next file) is responsible for delivering messages between
routers and ticking time forward. Routers themselves never touch the clock.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


INFINITY_RIP = 16
INFINITY_SARIP = 256 # as mentioned in the proposed protocol section


@dataclass
class RouteEntry:
    """One entry in a routing table."""
    next_hop: str       
    metric: int         
    seq_num: int = 0    


class Router:
    """A single router participating in either RIP or SA-RIP."""

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

        self.routing_table[self.name] = RouteEntry(next_hop=self.name, metric=0)


    # ------------------------------------------------------------------

    def neighbors(self):
        """Live neighbors right now, based on the current graph state."""
        return list(self.graph.neighbors(self.name))

    def link_cost(self, neighbor: str) -> int:
        """
        Cost of the direct link to a neighbor.

        For RIP: always 1 (hop count).
        For SA-RIP: we use the link delay as a stand-in for the αH+βD+γC metric.
                    (Hop count is implicit in summation; congestion is constant
                    for this experiment, so we hold it out for simplicity.)
        """
        if not self.graph.has_edge(self.name, neighbor):
            return INFINITY_RIP if self.mode == "RIP" else INFINITY_SARIP
        if self.mode == "RIP":
            return 1
        else:
            return self.graph[self.name][neighbor]["delay"]

    def infinity(self) -> int:
        return INFINITY_RIP if self.mode == "RIP" else INFINITY_SARIP

  
    # ------------------------------------------------------------------

    def build_full_update(self):
        """
        Build a full routing-table update (sent by RIP every 30s).
        Returns a list of (destination, metric) tuples.
        Split horizon is applied per-neighbor when sending (see send_update).
        """
        return [(dest, entry.metric) for dest, entry in self.routing_table.items()]

    def build_changed_update(self, changed_destinations):
        """
        Build a partial update containing only the destinations whose routes
        recently changed (used by SA-RIP triggered updates).
        """
        return [(dest, self.routing_table[dest].metric)
                for dest in changed_destinations if dest in self.routing_table]

    def apply_split_horizon(self, update, recipient):
        """
        Don't tell a neighbor about routes you learned *from* that neighbor.
        Returns a filtered update list.
        """
        filtered = []
        for dest, metric in update:
            entry = self.routing_table.get(dest)
            if entry and entry.next_hop == recipient and dest != self.name:
                continue  # skip — this route was learned from `recipient`
            filtered.append((dest, metric))
        return filtered


    # ------------------------------------------------------------------

    def receive_update(self, sender: str, update, seq_num: int = 0):
        """
        Process a routing update from a neighbor.

        Returns a set of destinations whose routes changed in our table,
        so the simulator can trigger further updates (SA-RIP).
        """
        # SA-RIP: reject stale or replayed updates by sequence number
        if self.mode == "SA-RIP":
            last_seen = self.last_seen_seq.get(sender, -1)
            if seq_num <= last_seen:
                return set()  # discard
            self.last_seen_seq[sender] = seq_num

        link = self.link_cost(sender)
        changed = set()

        for dest, advertised_metric in update:
            if dest == self.name:
                continue  # don't learn a route to ourselves from neighbors

            new_metric = advertised_metric + link
            if new_metric > self.infinity():
                new_metric = self.infinity()

            current = self.routing_table.get(dest)

            # CASE 1: we have no route -> install this one
            if current is None:
                if new_metric < self.infinity():
                    self.routing_table[dest] = RouteEntry(
                        next_hop=sender, metric=new_metric, seq_num=seq_num)
                    changed.add(dest)

            # CASE 2: update came from the current next-hop -> always trust it
            elif current.next_hop == sender:
                if new_metric != current.metric:
                    # If the route just became unreachable, SA-RIP tries backup first
                    if (self.mode == "SA-RIP"
                            and new_metric >= self.infinity()
                            and dest in self.backup_table):
                        backup = self.backup_table.pop(dest)
                        self.routing_table[dest] = backup
                    else:
                        current.metric = new_metric
                        current.seq_num = seq_num
                    changed.add(dest)

            # CASE 3: alternative route from a different neighbor
            else:
                if new_metric < current.metric:
                    # New route is better — demote the old one to backup (SA-RIP)
                    if self.mode == "SA-RIP":
                        self.backup_table[dest] = current
                    self.routing_table[dest] = RouteEntry(
                        next_hop=sender, metric=new_metric, seq_num=seq_num)
                    changed.add(dest)
                elif self.mode == "SA-RIP":
                    # Worse than primary, but might be a useful backup
                    backup = self.backup_table.get(dest)
                    if backup is None or new_metric < backup.metric:
                        self.backup_table[dest] = RouteEntry(
                            next_hop=sender, metric=new_metric, seq_num=seq_num)

        if changed:
            self.dirty = True
        return changed


    # ------------------------------------------------------------------

    def handle_link_failure(self, dead_neighbor: str):
        """
        Called by the simulator when a directly-connected link goes down.
        Returns the set of destinations whose routes were invalidated.
        """
        affected = set()

        # Find every routing entry that uses the dead neighbor as next-hop
        for dest, entry in list(self.routing_table.items()):
            if entry.next_hop == dead_neighbor:
                # SA-RIP: try promoting the backup route immediately
                if self.mode == "SA-RIP" and dest in self.backup_table:
                    backup = self.backup_table.pop(dest)
                    # Make sure the backup doesn't also depend on the dead neighbor
                    if backup.next_hop != dead_neighbor:
                        self.routing_table[dest] = backup
                        affected.add(dest)
                        continue
                # No backup (or backup also broken): poison this route
                entry.metric = self.infinity()
                affected.add(dest)

        if affected:
            self.dirty = True
        return affected


    # ------------------------------------------------------------------

    def known_destinations(self):
        """Destinations this router currently believes are reachable."""
        return {d for d, e in self.routing_table.items() if e.metric < self.infinity()}

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
    print(f"R0's table now:")
    for dest, entry in r0.routing_table.items():
        print(f"  {dest}: via {entry.next_hop}, metric {entry.metric}")