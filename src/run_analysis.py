import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from network import build_topology_8, build_topology_14
from simulator import Simulator


os.makedirs("results", exist_ok=True)


def run_single_experiment(topology_builder, failed_link):
    results = []

    for mode in ["RIP", "SA-RIP"]:
        graph = topology_builder()
        sim = Simulator(graph, mode=mode)

        initial_convergence = sim.run_until_converged()

        messages_before_failure = sim.message_count
        entries_before_failure = sim.route_entry_count
        time_before_failure = sim.time

        sim.fail_link(*failed_link)

        if mode == "RIP":
            failure_recovery_time = sim.run_until_converged() - time_before_failure
        else:
            failure_recovery_time = sim.time - time_before_failure

        results.append({
            "Protocol": mode,
            "Initial Convergence Time": initial_convergence,
            "Failure Recovery Time": failure_recovery_time,
            "Total Messages": sim.message_count,
            "Messages After Failure": sim.message_count - messages_before_failure,
            "Total Route Entries Advertised": sim.route_entry_count,
            "Route Entries After Failure": sim.route_entry_count - entries_before_failure
        })

    return pd.DataFrame(results)


def get_values(df8, df14, metric):
    rip_values = [
        df8[df8["Protocol"] == "RIP"][metric].values[0],
        df14[df14["Protocol"] == "RIP"][metric].values[0],
    ]

    sarip_values = [
        df8[df8["Protocol"] == "SA-RIP"][metric].values[0],
        df14[df14["Protocol"] == "SA-RIP"][metric].values[0],
    ]

    return rip_values, sarip_values


def grouped_bar_chart(df8, df14, metric, ylabel, title):
    topologies = ["8 Router", "14 Router"]
    rip_data, sarip_data = get_values(df8, df14, metric)

    x = np.arange(len(topologies))
    width = 0.35

    plt.figure(figsize=(7, 5))

    plt.bar(x - width / 2, rip_data, width, label="RIP")
    plt.bar(x + width / 2, sarip_data, width, label="SA-RIP")

    plt.xticks(x, topologies)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    df8 = run_single_experiment(
        build_topology_8,
        ("R4", "R7")
    )

    df14 = run_single_experiment(
        build_topology_14,
        ("R4", "R11")
    )

    print("\n8-Router Topology Results")
    print(df8)

    print("\n14-Router Topology Results")
    print(df14)

    df8.to_csv("results/performance_8.csv", index=False)
    df14.to_csv("results/performance_14.csv", index=False)

    grouped_bar_chart(
        df8,
        df14,
        "Initial Convergence Time",
        "Initial Convergence Time (Rounds)",
        "Initial Convergence Time Comparison"
    )

    grouped_bar_chart(
        df8,
        df14,
        "Failure Recovery Time",
        "Failure Recovery Time (Rounds)",
        "Failure Recovery Time Comparison"
    )

    grouped_bar_chart(
        df8,
        df14,
        "Messages After Failure",
        "Messages After Failure",
        "Routing Messages After Failure"
    )

    grouped_bar_chart(
        df8,
        df14,
        "Route Entries After Failure",
        "Route Entries Advertised",
        "Routing Overhead After Failure"
    )