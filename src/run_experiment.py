"""
run_experiment.py
-----------------
This file runs the full experiment: every possible single-link failure on each topology
for both RIP and SA-RIP, then produces summary CSVs and plots for the report.
"""

import csv
import os
import sys
import numpy as np
import matplotlib.pyplot as plt


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import build_topology_8, build_topology_14
from simulator import Simulator, MAX_SIM_TIME


RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_trial(graph_builder, link, mode):
    """Run one (graph, link, mode) trial. Returns (convergence_time, msg_count)."""
    g = graph_builder()
    sim = Simulator(g, mode=mode)
    result = sim.run(link_to_kill=link, failure_at=35.0)
    ct = result["convergence_time"]
    # Treat non-convergence as the max sim window for plotting purposes
    if ct is None:
        ct = MAX_SIM_TIME - 35.0
    return ct, result["update_count"]


def run_topology(name, graph_builder):
    """Run every single-link failure on this topology, both protocols."""
    g = graph_builder()
    links = list(g.edges())

    rip_times, sarip_times = [], []
    rip_msgs, sarip_msgs = [], []
    labels = []

    print(f"\n--- Topology: {name} ({len(links)} links) ---")
    for u, v in links:
        rt, rm = run_trial(graph_builder, (u, v), "RIP")
        st, sm = run_trial(graph_builder, (u, v), "SA-RIP")
        rip_times.append(rt)
        sarip_times.append(st)
        rip_msgs.append(rm)
        sarip_msgs.append(sm)
        labels.append(f"{u}-{v}")
        print(f"  {u}-{v:4s}  RIP: {rt:6.2f}s ({rm:3d} msgs)   "
              f"SA-RIP: {st:5.2f}s ({sm:3d} msgs)")

    return {
        "name": name,
        "labels": labels,
        "rip_times": rip_times,
        "sarip_times": sarip_times,
        "rip_msgs": rip_msgs,
        "sarip_msgs": sarip_msgs,
    }


def save_csv(data, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["topology", "link", "rip_convergence_s",
                         "sarip_convergence_s", "rip_post_failure_msgs",
                         "sarip_post_failure_msgs"])
        for d in data:
            for i, label in enumerate(d["labels"]):
                writer.writerow([d["name"], label,
                                 f"{d['rip_times'][i]:.3f}",
                                 f"{d['sarip_times'][i]:.3f}",
                                 d["rip_msgs"][i],
                                 d["sarip_msgs"][i]])
    print(f"Saved CSV to {path}")


def plot_convergence_bars(data, path):
    """Grouped bar chart: convergence time per failed link, RIP vs SA-RIP."""
    fig, axes = plt.subplots(len(data), 1, figsize=(12, 4 * len(data)))
    if len(data) == 1:
        axes = [axes]

    for ax, d in zip(axes, data):
        x = np.arange(len(d["labels"]))
        width = 0.4
        ax.bar(x - width/2, d["rip_times"], width, label="RIP",
               color="#d6604d", edgecolor="black")
        ax.bar(x + width/2, d["sarip_times"], width, label="SA-RIP",
               color="#4393c3", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(d["labels"], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Convergence time (s, log scale)")
        ax.set_yscale("log")
        ax.set_ylim(bottom=0.01)  # Avoid log(0) issues; clamp tiny bars
        ax.set_title(f"Convergence time after each link failure — {d['name']}")
        ax.legend()
        ax.grid(axis="y", which="both", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot to {path}")


def plot_message_bars(data, path):
    fig, axes = plt.subplots(len(data), 1, figsize=(12, 4 * len(data)))
    if len(data) == 1:
        axes = [axes]

    for ax, d in zip(axes, data):
        x = np.arange(len(d["labels"]))
        width = 0.4
        ax.bar(x - width/2, d["rip_msgs"], width, label="RIP",
               color="#d6604d", edgecolor="black")
        ax.bar(x + width/2, d["sarip_msgs"], width, label="SA-RIP",
               color="#4393c3", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(d["labels"], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Post-failure messages")
        ax.set_title(f"Post-failure routing messages — {d['name']}")
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot to {path}")


def plot_summary(data, path):
    """Box-plot summary across all link-failure trials."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Convergence time
    all_data = []
    all_labels = []
    for d in data:
        all_data.append(d["rip_times"])
        all_data.append(d["sarip_times"])
        all_labels.append(f"RIP\n{d['name']}")
        all_labels.append(f"SA-RIP\n{d['name']}")
    axes[0].boxplot(all_data, tick_labels=all_labels)
    axes[0].set_ylabel("Convergence time (s)")
    axes[0].set_title("Convergence Time Distribution")
    axes[0].set_yscale("log")
    axes[0].grid(axis="y", linestyle="--", alpha=0.5)

    # Messages
    all_data = []
    for d in data:
        all_data.append(d["rip_msgs"])
        all_data.append(d["sarip_msgs"])
    axes[1].boxplot(all_data, tick_labels=all_labels)
    axes[1].set_ylabel("Post-failure messages")
    axes[1].set_title("Post-failure Message Count Distribution")
    axes[1].grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot to {path}")


def print_summary_table(data):
    """Print a summary of mean/median/max convergence per topology."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for d in data:
        rip = np.array(d["rip_times"])
        sa = np.array(d["sarip_times"])
        print(f"\n{d['name']}:  ({len(d['labels'])} link-failure trials)")
        print(f"  RIP    convergence:  mean={rip.mean():6.2f}s  "
              f"median={np.median(rip):6.2f}s  max={rip.max():6.2f}s")
        print(f"  SA-RIP convergence:  mean={sa.mean():6.3f}s  "
              f"median={np.median(sa):6.3f}s  max={sa.max():6.3f}s")
        if sa.mean() > 0:
            speedup = rip.mean() / sa.mean()
            print(f"  SA-RIP is on average {speedup:.0f}x faster than RIP")


if __name__ == "__main__":
    data = [
        run_topology("8-router", build_topology_8),
        run_topology("14-router", build_topology_14),
    ]

    save_csv(data, os.path.join(RESULTS_DIR, "convergence_data.csv"))
    plot_convergence_bars(data, os.path.join(RESULTS_DIR, "convergence_comparison.png"))
    plot_message_bars(data, os.path.join(RESULTS_DIR, "message_comparison.png"))
    plot_summary(data, os.path.join(RESULTS_DIR, "summary_distribution.png"))
    print_summary_table(data)