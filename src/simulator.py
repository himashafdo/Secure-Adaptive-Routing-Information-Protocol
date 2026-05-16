"""
simulator.py
------------
Discrete-event simulator. RIP uses periodic 30s full-table updates.
SA-RIP uses triggered updates only, with poison reverse.
"""

import heapq
import networkx as nx
from router import Router

RIP_UPDATE_INTERVAL = 30.0
LINK_PROPAGATION    = 0.05
MAX_SIM_TIME        = 300.0
SARIP_BOOTSTRAP_ROUNDS = 8


class Simulator:
    def __init__(self, graph, mode):
        assert mode in ("RIP", "SA-RIP")
        self.graph = graph.copy()
        self.mode = mode
        self.now = 0.0
        self.events = []
        self._event_counter = 0

        self.routers = {n: Router(n, self.graph, mode=mode) for n in self.graph.nodes()}

        self.convergence_time = None
        self.failure_time = None
        self.update_count = 0

    def schedule(self, delay, cb):
        self._event_counter += 1
        heapq.heappush(self.events, (self.now + delay, self._event_counter, cb))

    def send_update(self, sender, recipient, payload, seq_num):
        if not payload:
            return
        if self.failure_time is not None:
            self.update_count += 1

        def deliver():
            r = self.routers[recipient]
            if not self.graph.has_edge(sender, recipient):
                return
            changed = r.receive_update(sender, payload, seq_num)
            if self.mode == "SA-RIP" and changed:
                r.dirty = False
                self._send_full_update(r)
        self.schedule(LINK_PROPAGATION, deliver)

    def _send_full_update(self, router):
        router.my_seq_num += 1
        for nb in router.neighbors():
            payload = router.build_full_update()
            payload = router.apply_poison_reverse(payload, nb)
            self.send_update(router.name, nb, payload, router.my_seq_num)

    def _schedule_rip_periodic(self):
        def fire():
            for r in self.routers.values():
                self._send_full_update(r)
            self.schedule(RIP_UPDATE_INTERVAL, fire)
        self.schedule(0.0, fire)

    def _bootstrap_sarip(self):
        for i in range(SARIP_BOOTSTRAP_ROUNDS):
            def fire():
                for r in self.routers.values():
                    self._send_full_update(r)
            self.schedule(i * LINK_PROPAGATION * 2, fire)

    def kill_link(self, u, v):
        if not self.graph.has_edge(u, v):
            return
        self.graph.remove_edge(u, v)
        self.failure_time = self.now

        ru = self.routers[u]
        rv = self.routers[v]
        ru.handle_link_failure(v)
        rv.handle_link_failure(u)

        if self.mode == "SA-RIP":
            self._send_full_update(ru)
            self._send_full_update(rv)

    def has_converged(self, verbose=False):
        """Compare each router's routing table to ground-truth shortest paths."""
        # Build a weighted graph using the protocol's own link cost,
        # so 'truth' uses the same metric the routers use.
        weighted = nx.Graph()
        for u, v in self.graph.edges():
            cost = self.routers[u].link_cost(v)
            weighted.add_edge(u, v, w=cost)

        mismatches = []
        for src in self.graph.nodes():
            router = self.routers[src]
            if self.mode == "RIP":
                truth = nx.single_source_shortest_path_length(self.graph, src)
            else:
                truth = nx.single_source_dijkstra_path_length(
                    weighted, src, weight="w")

            for dest in self.graph.nodes():
                t = truth.get(dest)
                e = router.routing_table.get(dest)
                b = e.metric if (e and e.metric < router.infinity()) else None

                if t is None and b is None:
                    continue
                if t is None or b is None:
                    mismatches.append((src, dest, t, b,
                                       e.next_hop if e else "?"))
                    continue
                if abs(t - b) > 1e-6:
                    mismatches.append((src, dest, t, b, e.next_hop))

        if verbose and mismatches:
            print(f"\n[t={self.now:.3f}] {len(mismatches)} mismatches:")
            for src, dest, t, b, via in mismatches[:20]:
                print(f"  {src} -> {dest}: believed={b} via {via}, truth={t}")
        return len(mismatches) == 0

    def run(self, link_to_kill=None, failure_at=35.0):
        if self.mode == "RIP":
            self._schedule_rip_periodic()
        else:
            self._bootstrap_sarip()

        if link_to_kill is not None:
            u, v = link_to_kill
            self.schedule(failure_at - self.now, lambda: self.kill_link(u, v))

        while self.events and self.now < MAX_SIM_TIME:
            time, _, cb = heapq.heappop(self.events)
            self.now = time
            cb()
            if self.failure_time is not None and self.convergence_time is None:
                if self.has_converged():
                    self.convergence_time = self.now - self.failure_time
                    break

        return {
            "mode": self.mode,
            "convergence_time": self.convergence_time,
            "failure_time": self.failure_time,
            "final_time": self.now,
            "update_count": self.update_count,
        }


if __name__ == "__main__":
    from network import build_topology_8, build_topology_14

    print("=" * 70)
    print("8-router topology")
    print("=" * 70)
    for link in [("R3", "R4"), ("R0", "R4"), ("R4", "R7"),
                 ("R1", "R4"), ("R2", "R5"), ("R6", "R7")]:
        print(f"\n  Killing link {link} at t=35s")
        for mode in ["RIP", "SA-RIP"]:
            g = build_topology_8()
            sim = Simulator(g, mode=mode)
            result = sim.run(link_to_kill=link, failure_at=35.0)
            ct = result["convergence_time"]
            ct_str = f"{ct:.3f} s" if ct is not None else "DID NOT CONVERGE"
            print(f"    {mode:7s}  conv: {ct_str:22s}  msgs: {result['update_count']}")
            if ct is None:
                sim.has_converged(verbose=True)

    print()
    print("=" * 70)
    print("14-router topology")
    print("=" * 70)
    for link in [("R0", "R1"), ("R2", "R9"), ("R6", "R13"),
                 ("R10", "R11"), ("R0", "R7"), ("R5", "R12")]:
        print(f"\n  Killing link {link} at t=35s")
        for mode in ["RIP", "SA-RIP"]:
            g = build_topology_14()
            sim = Simulator(g, mode=mode)
            result = sim.run(link_to_kill=link, failure_at=35.0)
            ct = result["convergence_time"]
            ct_str = f"{ct:.3f} s" if ct is not None else "DID NOT CONVERGE"
            print(f"    {mode:7s}  conv: {ct_str:22s}  msgs: {result['update_count']}")
            if ct is None:
                sim.has_converged(verbose=True)