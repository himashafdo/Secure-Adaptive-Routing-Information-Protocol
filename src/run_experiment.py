"""
run_experiment.py
-----------------
This is the main driver script. It runs the simulation for every possible
single link failure on both topologies, for both protocols (RIP and SA-RIP),
saves all the numbers to a CSV, and produces the plots we put in the report.

Basically: run it once, get all the results in results/.
"""

import csv
import os
import sys
import numpy as np
import matplotlib.pyplot as plt


# Make sure Python can find network.py and simulator.py even when we run
# this file from the repo root (e.g. "python src/run_experiment.py").

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import build_topology_8, build_topology_14
from simulator import Simulator, MAX_SIM_TIME


# Everything we save (CSVs, PNGs) goes into this folder
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


def run_trial(graph_builder, link, mode):


    """
    Run one experiment: build a fresh topology, kill the given link at t=35s,
    and measure how RIP or SA-RIP handled it.

    Returns a dict with the four numbers we care about:
    - initial convergence time (before failure)
    - failure recovery time (how long until everything is correct again)
    - how many messages were sent after the failure
    - how many total route entries were advertised after the failure
    """
    g = graph_builder()
    sim = Simulator(g, mode=mode)
    result = sim.run(link_to_kill=link, failure_at=35.0)

    # If the protocol didn't converge in time, treat it as "took the whole window"
    # so the plots still show something instead of crashing on a None.

    ct = result["convergence_time"]
    if ct is None:
        ct = MAX_SIM_TIME - 35.0

    # Same idea for initial convergence — shouldn't really happen but just in case
    
    ic = result["initial_convergence_time"]
    if ic is None:
        ic = 35.0  # never converged before failure (shouldn't happen)

    return {
        "convergence_time": ct,
        "initial_convergence": ic,
        "post_failure_msgs": result["update_count"],
        "post_failure_entries": result["entry_count"],
    }


def run_topology(name, graph_builder):
    """
    Run a trial for every single link in this topology, for both RIP and SA-RIP.
    Collects everything into one big dict so we can plot/save it later.
    Prints progress to the terminal as it goes.
    """

    g = graph_builder()
    links = list(g.edges())

    data = {
        "name": name,
        "labels": [],   # e.g. "R0-R1" for the x-axis
        "rip_conv": [], "sarip_conv": [], #recoverry time
        "rip_init": [], "sarip_init": [], #initial convergence time (before failure)
        "rip_msgs": [], "sarip_msgs": [], #messages sent after failure
        "rip_entries": [], "sarip_entries": [], #route entries advertised after failure
    }

    print(f"\n--- Topology: {name} ({len(links)} links) ---")
    for u, v in links:
        rip = run_trial(graph_builder, (u, v), "RIP")
        sa = run_trial(graph_builder, (u, v), "SA-RIP")
        data["labels"].append(f"{u}-{v}")
        data["rip_conv"].append(rip["convergence_time"])
        data["sarip_conv"].append(sa["convergence_time"])
        data["rip_init"].append(rip["initial_convergence"])
        data["sarip_init"].append(sa["initial_convergence"])
        data["rip_msgs"].append(rip["post_failure_msgs"])
        data["sarip_msgs"].append(sa["post_failure_msgs"])
        data["rip_entries"].append(rip["post_failure_entries"])
        data["sarip_entries"].append(sa["post_failure_entries"])
        print(f"  {u}-{v:5s}  RIP conv:{rip['convergence_time']:7.2f}s  msgs:{rip['post_failure_msgs']:4d}  "
              f"SA-RIP conv:{sa['convergence_time']:6.2f}s  msgs:{sa['post_failure_msgs']:4d}")

    return data


def save_csv(data, path):

    """
    Dump all the raw numbers to a CSV file so we can look at them later
    or open them in Excel.
    """

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["topology", "link",
                    "rip_initial_conv", "sarip_initial_conv",
                    "rip_recovery_s", "sarip_recovery_s",
                    "rip_post_failure_msgs", "sarip_post_failure_msgs",
                    "rip_post_failure_entries", "sarip_post_failure_entries"])
        for d in data:
            for i, lbl in enumerate(d["labels"]):
                w.writerow([d["name"], lbl,
                            f"{d['rip_init'][i]:.3f}",
                            f"{d['sarip_init'][i]:.3f}",
                            f"{d['rip_conv'][i]:.3f}",
                            f"{d['sarip_conv'][i]:.3f}",
                            d["rip_msgs"][i], d["sarip_msgs"][i],
                            d["rip_entries"][i], d["sarip_entries"][i]])
    print(f"Saved CSV to {path}")


def _grouped_bar(ax, labels, rip_vals, sarip_vals, ylabel, title, log=False):

    """
    Helper that draws one grouped bar chart on a given matplotlib axis.
    Two bars per x position: RIP (red) and SA-RIP (blue).
    Used by both plot_metric and (in spirit) plot_means.
    """

    x = np.arange(len(labels))
    w = 0.4
    ax.bar(x - w/2, rip_vals, w, label="RIP",
           color="#d6604d", edgecolor="black")
    ax.bar(x + w/2, sarip_vals, w, label="SA-RIP",
           color="#4393c3", edgecolor="black")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log:
        ax.set_yscale("log")
        ax.set_ylim(bottom=0.01)
    ax.legend()
    ax.grid(axis="y", which="both", linestyle="--", alpha=0.5)


def plot_metric(data, rip_key, sarip_key, ylabel, title_suffix, fname, log=False):

    """
    Plot one metric (e.g. recovery time) for both topologies, one subplot each.
    Saves the resulting PNG to results/<fname>.
    """

    fig, axes = plt.subplots(len(data), 1, figsize=(12, 4 * len(data)))
    if len(data) == 1:
        axes = [axes]
    for ax, d in zip(axes, data):
        _grouped_bar(ax, d["labels"], d[rip_key], d[sarip_key],
                     ylabel, f"{title_suffix} — {d['name']}", log=log)
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, fname)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot to {path}")


def plot_means(data, fname):
    """
    The 'summary at a glance' chart. Four panels, one for each metric.
    Each panel has just two pairs of bars (one pair per topology),
    showing the mean across all the trials for that topology.

    This is the chart that goes in the report's Performance Analysis section.
    """

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    metrics = [
        ("init", "Initial convergence time (s)", False),
        ("conv", "Failure recovery time (s)", True),
        ("msgs", "Post-failure messages", False),
        ("entries", "Post-failure route entries advertised", False),
    ]
    topo_names = [d["name"] for d in data]
    x = np.arange(len(topo_names))
    w = 0.35

    for ax, (key, ylabel, log) in zip(axes.flat, metrics):
        rip_means = [np.mean(d[f"rip_{key}"]) for d in data]
        sarip_means = [np.mean(d[f"sarip_{key}"]) for d in data]
        ax.bar(x - w/2, rip_means, w, label="RIP",
               color="#d6604d", edgecolor="black")
        ax.bar(x + w/2, sarip_means, w, label="SA-RIP",
               color="#4393c3", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(topo_names)
        ax.set_ylabel(ylabel)
        ax.set_title(ylabel)
        if log:
            ax.set_yscale("log")
            ax.set_ylim(bottom=0.01)
        ax.legend()
        ax.grid(axis="y", which="both", linestyle="--", alpha=0.5)
    plt.suptitle("Mean values across all link-failure trials", y=1.00, fontsize=14)
    plt.tight_layout()
    path = os.path.join(RESULTS_DIR, fname)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved plot to {path}")


def print_summary(data):

    """
    Print a nice summary table at the end so we can copy the headline numbers
    straight into the report without opening the CSV.
    """

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for d in data:
        rconv = np.array(d["rip_conv"]); sconv = np.array(d["sarip_conv"])
        rmsg  = np.array(d["rip_msgs"]); smsg  = np.array(d["sarip_msgs"])
        rent  = np.array(d["rip_entries"]); sent = np.array(d["sarip_entries"])
        rinit = np.array(d["rip_init"]); sinit = np.array(d["sarip_init"])
        print(f"\n{d['name']} ({len(d['labels'])} trials)")
        print(f"  Initial conv (mean):  RIP {rinit.mean():.2f}s  SA-RIP {sinit.mean():.2f}s")
        print(f"  Recovery (mean):      RIP {rconv.mean():.2f}s  SA-RIP {sconv.mean():.3f}s   "
              f"({rconv.mean()/sconv.mean():.0f}x faster)")
        print(f"  Msgs after failure:   RIP {rmsg.mean():.0f}    SA-RIP {smsg.mean():.0f}     "
              f"({rmsg.mean()/smsg.mean():.1f}x fewer)")
        print(f"  Entries after failure:RIP {rent.mean():.0f}    SA-RIP {sent.mean():.0f}     "
              f"({rent.mean()/sent.mean():.1f}x fewer)")


if __name__ == "__main__":
    data = [
        run_topology("8-router", build_topology_8),
        run_topology("14-router", build_topology_14),
    ]
    save_csv(data, os.path.join(RESULTS_DIR, "convergence_data.csv"))

    # Per-link bar charts
    plot_metric(data, "rip_init", "sarip_init",
                "Initial convergence time (s)",
                "Initial convergence time before failure",
                "initial_convergence_per_link.png")
    plot_metric(data, "rip_conv", "sarip_conv",
                "Recovery time (s, log scale)",
                "Failure recovery time",
                "recovery_per_link.png", log=True)
    plot_metric(data, "rip_msgs", "sarip_msgs",
                "Post-failure messages",
                "Routing messages after failure",
                "messages_per_link.png")
    plot_metric(data, "rip_entries", "sarip_entries",
                "Post-failure route entries advertised",
                "Routing overhead (entries) after failure",
                "entries_per_link.png")

    # Mean-value summary chart
    plot_means(data, "summary_means.png")


    # Print the final speedup numbers so we can put them in Section 4
    print_summary(data)