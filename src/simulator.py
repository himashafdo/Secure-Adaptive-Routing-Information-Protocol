from collections import deque
from router import Router


class Simulator:
    def __init__(self, graph, mode="RIP"):
        self.graph = graph
        self.mode = mode

        self.routers = {
            node: Router(node, graph, mode=mode)
            for node in graph.nodes()
        }

        self.time = 0
        self.message_count = 0
        self.route_entry_count = 0
        self.history = []

    def send_update(self, sender_name, recipient_name, changed_destinations=None):
        sender = self.routers[sender_name]
        recipient = self.routers[recipient_name]

        if changed_destinations is None:
            update = sender.build_full_update()
        else:
            update = sender.build_changed_update(changed_destinations)

        update = sender.apply_split_horizon(update, recipient_name)

        if not update:
            return set()

        sender.my_seq_num += 1
        seq_num = sender.my_seq_num

        changed = recipient.receive_update(sender_name, update, seq_num)

        self.message_count += 1
        self.route_entry_count += len(update)

        return changed

    def run_periodic_round(self):
        total_changed = set()

        for sender_name, router in self.routers.items():
            for neighbor in router.neighbors():
                changed = self.send_update(sender_name, neighbor)
                total_changed.update(changed)

        self.time += 1
        self.record_state()

        return total_changed

    def run_until_converged(self, max_rounds=100):
        stable_rounds = 0

        for _ in range(max_rounds):
            changed = self.run_periodic_round()

            if not changed:
                stable_rounds += 1
            else:
                stable_rounds = 0

            if stable_rounds >= 3:
                return self.time

        return self.time

    def run_triggered_until_stable(self, initial_events, max_steps=1000):
        """
        SA-RIP event-driven triggered update propagation.

        initial_events:
            deque/list of (sender_name, changed_destinations)
        """
        queue = deque(initial_events)
        steps = 0

        while queue and steps < max_steps:
            sender_name, changed_destinations = queue.popleft()
            sender = self.routers[sender_name]

            for neighbor in sender.neighbors():
                new_changes = self.send_update(
                    sender_name,
                    neighbor,
                    changed_destinations
                )

                if new_changes:
                    queue.append((neighbor, new_changes))

            steps += 1

        self.time += 1
        self.record_state()

        return self.time

    def fail_link(self, u, v):
        if self.graph.has_edge(u, v):
            self.graph.remove_edge(u, v)

        affected_u = self.routers[u].handle_link_failure(v)
        affected_v = self.routers[v].handle_link_failure(u)

        if self.mode == "SA-RIP":
            events = []

            if affected_u:
                events.append((u, affected_u))

            if affected_v:
                events.append((v, affected_v))

            self.run_triggered_until_stable(events)

        else:
            self.record_state()

    def record_state(self):
        reachable_counts = {
            name: len(router.known_destinations())
            for name, router in self.routers.items()
        }

        self.history.append({
            "time": self.time,
            "messages": self.message_count,
            "route_entries": self.route_entry_count,
            "reachable_avg": sum(reachable_counts.values()) / len(reachable_counts)
        })