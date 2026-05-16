"""
router.py
---------
Router model for the SA-RIP vs RIP simulation.

Each router stores:
  - The most recent distance vector advertised by each neighbor
  - A derived routing table (primary + backup) recomputed from those vectors
  - Sequence numbers per neighbor (SA-RIP only)

Two modes:
  - "RIP"    : full-table updates every 30s, hop-count metric
  - "SA-RIP" : triggered updates on change, link-delay metric, backup cache
"""

from dataclasses import dataclass
from typing import Dict


INFINITY_RIP = 16
INFINITY_SARIP = 256


@dataclass
class RouteEntry:
    next_hop: str
    metric: int


class Router:
    def __init__(self, name, graph, mode="RIP"):
        assert mode in ("RIP", "SA-RIP")
        self.name = name
        self.graph = graph
        self.mode = mode

        # Each neighbor's most recently advertised distance vector:
        #   neighbor_name -> {destination: metric}
        self.neighbor_vectors: Dict[str, Dict[str, int]] = {}

        # Derived tables
        self.routing_table: Dict[str, RouteEntry] = {}
        self.backup_table: Dict[str, RouteEntry] = {}

        # Sequence numbers
        self.my_seq_num = 0
        self.last_seen_seq: Dict[str, int] = {}

        # The router always knows about itself
        self.routing_table[self.name] = RouteEntry(self.name, 0)

        self.dirty = False

    # ---------- helper funcs ----------

    def neighbors(self):
        return list(self.graph.neighbors(self.name))

    # SA-RIP weighting constants for adaptive metric αH + βD + γC
    ALPHA = 1.0    # hop count weight
    BETA  = 0.1    # delay weight
    GAMMA = 0.5    # congestion/capacity weight

    def link_cost(self, nb):
        if not self.graph.has_edge(self.name, nb):
            return self.infinity()
        if self.mode == "RIP":
            return 1
        # SA-RIP adaptive metric: αH + βD + γC
        hop_cost = 1
        delay = self.graph[self.name][nb]["delay"]
        capacity = self.graph[self.name][nb]["capacity"]
        congestion_cost = 100 / capacity  # lower capacity = more congestion
        metric = self.ALPHA * hop_cost + self.BETA * delay + self.GAMMA * congestion_cost
        return max(1, int(round(metric)))

    def infinity(self):
        return INFINITY_RIP if self.mode == "RIP" else INFINITY_SARIP

    # ---------- building outgoing updates ----------

    def build_full_update(self):
        return [(d, e.metric) for d, e in self.routing_table.items()]

    def build_changed_update(self, changed):
        return [(d, self.routing_table[d].metric) for d in changed
                if d in self.routing_table]

    def apply_poison_reverse(self, update, recipient):
        """If a route was learned via `recipient`, advertise it as infinity."""
        out = []
        for dest, metric in update:
            entry = self.routing_table.get(dest)
            if entry and entry.next_hop == recipient and dest != self.name:
                out.append((dest, self.infinity()))
            else:
                out.append((dest, metric))
        return out

    # ---------- receiving and recomputing ----------

    def receive_update(self, sender, update, seq_num=0):
        """
        Store sender's advertised distance vector, then recompute our table.
        Return the set of destinations whose primary route changed.
        """
        # SA-RIP: reject replays
        if self.mode == "SA-RIP":
            if seq_num <= self.last_seen_seq.get(sender, -1):
                return set()
            self.last_seen_seq[sender] = seq_num

        # Ignore updates from non-neighbors (link may have died)
        if not self.graph.has_edge(self.name, sender):
            return set()

        # Store the sender's vector (overwriting any older one)
        self.neighbor_vectors[sender] = {dest: metric for dest, metric in update}

        return self._recompute()

    def handle_link_failure(self, dead_nb):
        """Drop the dead neighbor's vector and recompute."""
        if dead_nb in self.neighbor_vectors:
            del self.neighbor_vectors[dead_nb]
        if dead_nb in self.last_seen_seq:
            del self.last_seen_seq[dead_nb]
        return self._recompute()

    def _recompute(self):
        """
        Bellman-Ford-style: derive primary + backup routing tables from
        the stored neighbor vectors and link costs.
        Returns set of destinations whose primary changed.
        """
        # Gather every destination we know about (from any neighbor + ourselves)
        all_dests = {self.name}
        for vec in self.neighbor_vectors.values():
            all_dests.update(vec.keys())

        new_routing = {self.name: RouteEntry(self.name, 0)}
        new_backup = {}

        for dest in all_dests:
            if dest == self.name:
                continue

            # Gather all candidate (next_hop, total_metric) options
            candidates = []
            for nb, vec in self.neighbor_vectors.items():
                if not self.graph.has_edge(self.name, nb):
                    continue
                adv = vec.get(dest, self.infinity())
                if adv >= self.infinity():
                    continue
                total = adv + self.link_cost(nb)
                if total >= self.infinity():
                    continue
                candidates.append((total, nb))

            if not candidates:
                continue  # destination unreachable

            candidates.sort()  # by metric ascending, then nb name
            best_metric, best_nb = candidates[0]
            new_routing[dest] = RouteEntry(best_nb, best_metric)

            # Backup: best candidate that uses a different next_hop
            for metric, nb in candidates[1:]:
                if nb != best_nb:
                    new_backup[dest] = RouteEntry(nb, metric)
                    break

        # Diff against old primary table to find what changed
        changed = set()
        old_dests = set(self.routing_table.keys())
        new_dests = set(new_routing.keys())

        for d in old_dests | new_dests:
            old = self.routing_table.get(d)
            new = new_routing.get(d)
            if old is None and new is not None:
                changed.add(d)
            elif old is not None and new is None:
                changed.add(d)
            elif old.metric != new.metric or old.next_hop != new.next_hop:
                changed.add(d)

        # Also include explicitly-poisoned destinations we no longer have
        for d in old_dests - new_dests:
            changed.add(d)

        self.routing_table = new_routing
        self.backup_table = new_backup

        if changed:
            self.dirty = True
        return changed

    def __repr__(self):
        return f"Router({self.name}, {self.mode})"


if __name__ == "__main__":
    from network import build_topology_8
    g = build_topology_8()
    r0 = Router("R0", g, mode="RIP")
    r1 = Router("R1", g, mode="RIP")
    print(r0, r1)
    changed = r0.receive_update("R1", r1.build_full_update(), seq_num=1)
    print("Changed:", changed)
    for d, e in r0.routing_table.items():
        print(f"  {d}: via {e.next_hop}, metric {e.metric}")