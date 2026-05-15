# Secure Adaptive RIP (SA-RIP) Simulation

EN2150 Communication Network Engineering — Routing Protocol Design Assignment
**Team TeraHertz** — University of Moratuwa

## Overview

This repository contains the Python simulation comparing **traditional RIP** against our proposed **Secure Adaptive RIP (SA-RIP)** protocol. The simulation demonstrates SA-RIP's improvement over RIP in terms of convergence time after link failures.

## Team Members

- Udana Athukorala (230063B)
- Bashitha Anthony (230159B)
- Himasha Fernando (230186E)
- Indeepa Perera (230395T)

## Repository Structure

```
.
├── src/
│   ├── network.py         # Topology generation
│   ├── router.py          # Router model (RIP + SA-RIP modes)
│   ├── simulator.py       # Discrete-event simulation engine
│   └── run_experiment.py  # Experiment driver — runs trials & plots
├── results/               # Generated CSVs and plots
├── requirements.txt
└── README.md
```

## How to Run

### Prerequisites

- Python 3.9+
- pip

### Setup

```bash
git clone https://github.com/himashafdo/Secure-Adaptive-Routing-Information-Protocol.git
cd Secure-Adaptive-Routing-Information-Protocol
python -m venv venv
source venv/bin/activate     # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the Experiment

```bash
python src/run_experiment.py
```

This runs the simulation on both 8-router and 14-router topologies, with many link-failure trials per topology, and saves results to `results/`.

## What the Simulation Shows

- A small/medium-sized network of routers runs distance-vector routing
- At a random time, a randomly chosen link is severed
- Both protocols are measured on **convergence time** — how long until every router in the network knows the new correct shortest paths

### Key Differences Implemented

| Behavior             | Traditional RIP                | SA-RIP                           |
| -------------------- | ------------------------------ | -------------------------------- |
| Periodic update      | Every 30 seconds (full table)  | Disabled (event-driven only)     |
| Failure notification | Waits for next periodic update | Triggered selective update       |
| Backup route         | None                           | Cached, activated instantly      |
| Loop prevention      | Split horizon only             | Split horizon + sequence numbers |

## Results Summary

(To be filled in after running experiments — see `results/convergence_comparison.png`)

## License

Academic project — University of Moratuwa, 2026.
