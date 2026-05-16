"""
network.py
----------
Builds the network topologies used in the SA-RIP vs RIP simulation.

Each topology is a NetworkX graph where:
  - Nodes are routers labeled R0, R1, R2, ...
  - Edges are bidirectional links with:
      * delay    : link propagation delay in milliseconds
      * capacity : link bandwidth in Mbps

Note:
Fixed random seeds are used so that the same topology gets the same
delay and capacity values every time. This makes RIP vs SA-RIP comparison fair.
"""

import os
import random
import networkx as nx


def build_topology_8():
    """8-router topology with redundant paths."""
    G = nx.Graph()

    edges = [
        ("R0", "R1"), ("R1", "R2"),
        ("R0", "R3"), ("R0", "R4"),
        ("R1", "R4"),
        ("R2", "R4"), ("R2", "R5"),
        ("R3", "R4"), ("R3", "R6"),
        ("R4", "R5"), ("R4", "R7"),
        ("R5", "R7"),
        ("R6", "R7"),
    ]

    G.add_edges_from(edges)
    _assign_link_properties(G, seed=42)

    return G


def build_topology_14():
    """14-router topology with two interconnected rings and cross-links."""
    G = nx.Graph()

    edges = [
        # outer ring
        ("R0", "R1"), ("R1", "R2"), ("R2", "R3"), ("R3", "R4"),
        ("R4", "R5"), ("R5", "R6"), ("R6", "R0"),

        # inner ring
        ("R7", "R8"), ("R8", "R9"), ("R9", "R10"),
        ("R10", "R11"), ("R11", "R12"), ("R12", "R13"), ("R13", "R7"),

        # cross-links between rings
        ("R0", "R7"), ("R2", "R9"),
        ("R4", "R11"), ("R6", "R13"),

        # extra shortcuts for redundancy
        ("R1", "R8"), ("R5", "R12"),
    ]

    G.add_edges_from(edges)
    _assign_link_properties(G, seed=123)

    return G


def _assign_link_properties(G, seed=None):
    """
    Attach reproducible delay and capacity values to each edge.

    delay    : 1 to 50 ms
    capacity : 10 or 100 Mbps
    """
    rng = random.Random(seed)

    for u, v in G.edges():
        G[u][v]["delay"] = rng.randint(1, 50)
        G[u][v]["capacity"] = rng.choice([10, 100])


def visualize(G, filename="results/topology.png", title="Network Topology"):
    """Save a PNG image of the topology with delay labels on edges."""
    import matplotlib.pyplot as plt

    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)

    pos = nx.spring_layout(G, seed=7)


if __name__ == "__main__":
    g8 = build_topology_8()
    g14 = build_topology_14()

    print(f"Topology 8:  {g8.number_of_nodes()} nodes, {g8.number_of_edges()} edges")
    print(f"Topology 14: {g14.number_of_nodes()} nodes, {g14.number_of_edges()} edges")

    print("\nSample edges from 8-router topology:")
    for u, v, d in list(g8.edges(data=True))[:5]:
        print(
            f"  {u} <-> {v}   "
            f"delay={d['delay']}ms  "
            f"capacity={d['capacity']}Mbps"
        )

    visualize(g8, "results/topology_8.png", "8-Router Topology")
    visualize(g14, "results/topology_14.png", "14-Router Topology")