# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import csv
import itertools
import logging
import pathlib
import random
import time
from statistics import mean, stdev
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

from mqt.sqr.placements.random_strategy import RandomPlacementStrategy
from mqt.sqr.routing.default_routing import DefaultRoutingPlanner
from mqt.sqr.routing.rotation_cycles_routing import HybridRotationRoutingPlanner
from mqt.sqr.routing.rotation_routing import RotationRoutingPlanner
from mqt.sqr.routing.routing_with_reroute import RerouteRoutingPlanner
from mqt.sqr.simulation import RoutingSimulator, SimulationConfig
from mqt.sqr.utils.network import NetworkBuilder

if TYPE_CHECKING:
    import networkx as nx

    from mqt.sqr.placements.placement_strategy import PlacementStrategy
    from mqt.sqr.routing.common import TimedNode
    from mqt.sqr.routing.routing_strategy import RoutingStrategy


logger = logging.getLogger(__name__)


def count_movements(timelines: dict[int, list[TimedNode]]) -> int:
    moves = 0
    for path in timelines.values():
        for (c1, _), (c2, _) in itertools.pairwise(path):
            if c1 != c2:
                moves += 1
    return moves


def total_timesteps(timelines: dict[int, list[TimedNode]]) -> int:
    max_t = 0
    for path in timelines.values():
        if path:
            max_t = max(max_t, path[-1][1])
    return max_t


def get_max_sn_nodes(width: int, height: int) -> int:
    graph: nx.Graph = NetworkBuilder.build_network(width, height)
    return sum(1 for _, data in graph.nodes(data=True) if data.get("type") == "SN")


def evaluate_strategy(
    routing_strategy: RoutingStrategy,
    n_qubits_list: list[int],
    n_samples: int = 20,
    width: int = 4,
    height: int = 4,
    rounds: int = 5,
    p_success: float = 0.99,
    p_repair: float = 0.25,
) -> tuple[list[float], list[float]]:

    placement: PlacementStrategy = RandomPlacementStrategy()

    avg_timesteps: list[float] = []
    avg_movements: list[float] = []

    strategy_dead = False

    for n_qubits in n_qubits_list:
        if strategy_dead:
            avg_timesteps.append(float("nan"))
            avg_movements.append(float("nan"))
            continue

        timesteps_samples: list[int] = []
        movements_samples: list[int] = []

        for sample_idx in range(n_samples):
            base_seed = 1000 * n_qubits + sample_idx
            random.seed(base_seed)

            config = SimulationConfig(
                width=width,
                height=height,
                n_qubits=n_qubits,
                rounds=rounds,
                p_success=p_success,
                p_repair=p_repair,
                seed=base_seed,
            )

            simulator = RoutingSimulator(
                placement_strategy=placement,
                routing_strategy=routing_strategy,
                config=config,
            )

            try:
                timelines, _ = simulator.run()
            except Exception:
                logger.exception("Simulation failed")
                continue

            timesteps_samples.append(total_timesteps(timelines))
            movements_samples.append(count_movements(timelines))

        if timesteps_samples:
            avg_timesteps.append(mean(timesteps_samples))
            avg_movements.append(mean(movements_samples))
        else:
            avg_timesteps.append(float("nan"))
            avg_movements.append(float("nan"))
            strategy_dead = True

    return avg_timesteps, avg_movements


def evaluate_strategy_vs_edge_expectation(
    routing_strategy: RoutingStrategy,
    expectation_values: list[float],
    n_qubits: int = 8,
    n_samples: int = 100,
    width: int = 3,
    height: int = 3,
    rounds: int = 5,
    min_expectation: float = 0.0,
) -> tuple[list[float], list[float]]:

    placement: PlacementStrategy = RandomPlacementStrategy()

    avg_timesteps: list[float] = []
    avg_movements: list[float] = []

    for idx_e, expectation in enumerate(expectation_values, start=1):
        if expectation < min_expectation:
            avg_timesteps.append(float("nan"))
            avg_movements.append(float("nan"))
            continue

        timesteps_samples: list[int] = []
        movements_samples: list[int] = []

        p_success = expectation
        p_repair = expectation

        for sample_idx in range(n_samples):
            base_seed = 10_000 * idx_e + sample_idx
            random.seed(base_seed)

            config = SimulationConfig(
                width=width,
                height=height,
                n_qubits=n_qubits,
                rounds=rounds,
                p_success=p_success,
                p_repair=p_repair,
                seed=base_seed,
            )

            simulator = RoutingSimulator(
                placement_strategy=placement,
                routing_strategy=routing_strategy,
                config=config,
            )

            try:
                timelines, _ = simulator.run()
            except Exception:
                logger.exception("Simulation failed")
                continue

            timesteps_samples.append(total_timesteps(timelines))
            movements_samples.append(count_movements(timelines))

        if timesteps_samples:
            avg_timesteps.append(mean(timesteps_samples))
            avg_movements.append(mean(movements_samples))
        else:
            avg_timesteps.append(float("nan"))
            avg_movements.append(float("nan"))

    return avg_timesteps, avg_movements


def evaluate_strategies_over_grids(
    routing_strategies: dict[str, RoutingStrategy],
    grid_sizes: list[tuple[int, int]],
    n_samples: int = 50,
    rounds: int = 5,
    p_success: float = 0.9,
    p_repair: float = 0.25,
) -> tuple[dict[str, list[float]], dict[str, list[float]], list[int]]:

    placement: PlacementStrategy = RandomPlacementStrategy()

    avg_timesteps: dict[str, list[float]] = {name: [] for name in routing_strategies}
    avg_movements: dict[str, list[float]] = {name: [] for name in routing_strategies}
    qubits_per_grid: list[int] = []

    for width, height in grid_sizes:
        n_sn = get_max_sn_nodes(width, height)
        n_qubits = 12 if (width, height) == (5, 5) else max(2, int(0.25 * n_sn))
        qubits_per_grid.append(n_qubits)

        for strat_name, routing_strategy in routing_strategies.items():
            timesteps_samples: list[int] = []
            movements_samples: list[int] = []

            for sample_idx in range(n_samples):
                base_seed = 100_000 * (width * 10 + height) + sample_idx
                random.seed(base_seed)

                config = SimulationConfig(
                    width=width,
                    height=height,
                    n_qubits=n_qubits,
                    rounds=rounds,
                    p_success=p_success,
                    p_repair=p_repair,
                    seed=base_seed,
                )

                simulator = RoutingSimulator(
                    placement_strategy=placement,
                    routing_strategy=routing_strategy,
                    config=config,
                )

                try:
                    timelines, _ = simulator.run()
                except Exception:
                    logger.exception("Simulation failed")
                    continue

                timesteps_samples.append(total_timesteps(timelines))
                movements_samples.append(count_movements(timelines))

            if timesteps_samples:
                avg_timesteps[strat_name].append(mean(timesteps_samples))
                avg_movements[strat_name].append(mean(movements_samples))
            else:
                avg_timesteps[strat_name].append(float("nan"))
                avg_movements[strat_name].append(float("nan"))

    return avg_timesteps, avg_movements, qubits_per_grid


def evaluate_placements_for_routing(
    routing_strategy: RoutingStrategy,
    placement_strategies: dict[str, PlacementStrategy],
    width: int = 3,
    height: int = 3,
    n_samples: int = 100,
    rounds: int = 5,
    p_success: float = 0.998,
    p_repair: float = 0.25,
    n_qubits: int = 8,
) -> tuple[dict[str, float], dict[str, float], int]:

    get_max_sn_nodes(width, height)

    avg_timesteps: dict[str, float] = {}
    avg_movements: dict[str, float] = {}

    for pname, placement in placement_strategies.items():
        timesteps_samples: list[int] = []
        movements_samples: list[int] = []

        for sample_idx in range(n_samples):
            base_seed = 1_000_000 * hash(pname) % (2**31 - 1) + sample_idx
            random.seed(base_seed)

            config = SimulationConfig(
                width=width,
                height=height,
                n_qubits=n_qubits,
                rounds=rounds,
                p_success=p_success,
                p_repair=p_repair,
                seed=base_seed,
            )

            simulator = RoutingSimulator(
                placement_strategy=placement,
                routing_strategy=routing_strategy,
                config=config,
            )

            try:
                timelines, _ = simulator.run()
            except Exception:
                logger.exception("Simulation failed")
                continue

            timesteps_samples.append(total_timesteps(timelines))
            movements_samples.append(count_movements(timelines))

        if timesteps_samples:
            avg_timesteps[pname] = mean(timesteps_samples)
            avg_movements[pname] = mean(movements_samples)
        else:
            avg_timesteps[pname] = float("nan")
            avg_movements[pname] = float("nan")

    return avg_timesteps, avg_movements, n_qubits


def evaluate_exception_rates_for_strategies_3x3(
    n_qubits_min: int = 2,
    n_qubits_max: int = 24,
    n_samples: int = 100,
    width: int = 3,
    height: int = 3,
    p_success: float = 0.998,
    p_repair: float = 0.25,
) -> dict[str, list[float]]:

    routing_strategies: dict[str, RoutingStrategy] = {
        "Default": DefaultRoutingPlanner(),
        "Reroute": RerouteRoutingPlanner(),
        "Rotation": RotationRoutingPlanner(),
        "HybridRotation": HybridRotationRoutingPlanner(),
    }

    placement: PlacementStrategy = RandomPlacementStrategy()

    n_qubits_list = list(range(n_qubits_min, n_qubits_max + 1))
    exception_rates: dict[str, list[float]] = {name: [] for name in routing_strategies}

    strategy_dead: dict[str, bool] = dict.fromkeys(routing_strategies, False)

    for n_qubits in n_qubits_list:
        for strat_name, routing_strategy in routing_strategies.items():
            if strategy_dead[strat_name]:
                exception_rates[strat_name].append(1.0)
                continue

            fail_count = 0

            for sample_idx in range(n_samples):
                base_seed = (hash(strat_name) & 0x7FFFFFFF) * 10_000 + n_qubits * 100 + sample_idx
                random.seed(base_seed)

                config = SimulationConfig(
                    width=width,
                    height=height,
                    n_qubits=n_qubits,
                    rounds=5,
                    p_success=p_success,
                    p_repair=p_repair,
                    seed=base_seed,
                )

                simulator = RoutingSimulator(
                    placement_strategy=placement,
                    routing_strategy=routing_strategy,
                    config=config,
                )

                try:
                    simulator.run()
                except Exception:
                    logger.exception("Simulation failed")
                    fail_count += 1

            rate = fail_count / n_samples
            exception_rates[strat_name].append(rate)

            if rate >= 1.0:
                strategy_dead[strat_name] = True

    plt.figure(figsize=(10, 6))
    for strat_name, rates in exception_rates.items():
        plt.plot(n_qubits_list, rates, marker="o", label=strat_name)

    plt.xlabel("Number of Qubits")
    plt.ylabel("Exception Rate")
    plt.title(
        "Exception Rate vs. Number of Qubits\n3x3 Grid, RandomPlacement, p_success=0.998, p_repair=0.25, 100 Samples"
    )
    plt.xticks(n_qubits_list, rotation=45)
    plt.ylim(-0.05, 1.05)
    plt.grid(visible=True, which="both", linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig("D:\\Uni\\failrate_qubits.png")
    plt.show()

    return exception_rates


def evaluate_exception_rates_vs_edge_expectation_3x3(
    expectation_values: list[float] | None = None,
    n_qubits: int = 6,
    n_samples: int = 20,
    width: int = 3,
    height: int = 3,
    rounds: int = 5,
) -> dict[str, list[float]]:
    if expectation_values is None:
        expectation_values = [round(1.0 - 0.025 * i, 3) for i in range(41)]

    routing_strategies: dict[str, RoutingStrategy] = {
        "Default": DefaultRoutingPlanner(),
        "Reroute": RerouteRoutingPlanner(),
        "Rotation": RotationRoutingPlanner(),
        "HybridRotation": HybridRotationRoutingPlanner(),
    }

    placement: PlacementStrategy = RandomPlacementStrategy()

    exception_rates: dict[str, list[float]] = {name: [] for name in routing_strategies}

    strategy_dead: dict[str, bool] = dict.fromkeys(routing_strategies, False)

    for e in expectation_values:
        p_success = e
        p_repair = e

        for strat_name, routing_strategy in routing_strategies.items():
            if strategy_dead[strat_name]:
                exception_rates[strat_name].append(1.0)
                continue

            fail_count = 0

            for _sample_idx in range(n_samples):
                base_seed = 42
                random.seed(base_seed)

                config = SimulationConfig(
                    width=width,
                    height=height,
                    n_qubits=n_qubits,
                    rounds=rounds,
                    p_success=p_success,
                    p_repair=p_repair,
                    seed=base_seed,
                )

                simulator = RoutingSimulator(
                    placement_strategy=placement,
                    routing_strategy=routing_strategy,
                    config=config,
                )

                try:
                    simulator.run()
                except Exception:
                    logger.exception("Simulation failed")
                    fail_count += 1

            rate = fail_count / n_samples
            exception_rates[strat_name].append(rate)

            if rate >= 1.0:
                strategy_dead[strat_name] = True

    e_sorted = sorted(expectation_values)

    plt.figure(figsize=(10, 6))
    for strat_name, rates in exception_rates.items():
        e_to_rate = dict(zip(expectation_values, rates, strict=False))
        rates_sorted = [e_to_rate[e] for e in e_sorted]

        plt.plot(e_sorted, rates_sorted, marker="o", label=strat_name)

    plt.xlabel("Expectation Value E of Working Edges")
    plt.ylabel("Exception Rate")
    plt.title(
        f"Exception Rate vs. Expectation Value E\n3x3 Grid, n_qubits={n_qubits}, RandomPlacement, 100 Samples per E"
    )
    plt.xticks(e_sorted, rotation=45)
    plt.ylim(-0.05, 1.05)
    plt.grid(visible=True, which="both", linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig("D:\\Uni\\failrate_expectation.png")
    plt.show()

    return exception_rates


def evaluate_runtimes_for_strategies_3x3(
    n_qubits_min: int = 2,
    n_qubits_max: int = 24,
    n_samples: int = 100,
    width: int = 3,
    height: int = 3,
    p_success: float = 0.998,
    p_repair: float = 0.25,
) -> dict[str, list[float]]:
    routing_strategies: dict[str, RoutingStrategy] = {
        "Default": DefaultRoutingPlanner(),
        "Reroute": RerouteRoutingPlanner(),
        "Rotation": RotationRoutingPlanner(),
        "HybridRotation": HybridRotationRoutingPlanner(),
    }

    placement: PlacementStrategy = RandomPlacementStrategy()

    n_qubits_list = list(range(n_qubits_min, n_qubits_max + 1))
    runtimes: dict[str, list[float]] = {name: [] for name in routing_strategies}

    strategy_dead: dict[str, bool] = dict.fromkeys(routing_strategies, False)

    for n_qubits in n_qubits_list:
        for strat_name, routing_strategy in routing_strategies.items():
            if strategy_dead[strat_name]:
                runtimes[strat_name].append(float("nan"))
                continue

            sample_runtimes: list[float] = []
            fail_count = 0

            for sample_idx in range(n_samples):
                base_seed = (hash(strat_name) & 0x7FFFFFFF) * 10_000 + n_qubits * 100 + sample_idx
                random.seed(base_seed)

                config = SimulationConfig(
                    width=width,
                    height=height,
                    n_qubits=n_qubits,
                    rounds=5,
                    p_success=p_success,
                    p_repair=p_repair,
                    seed=base_seed,
                )

                simulator = RoutingSimulator(
                    placement_strategy=placement,
                    routing_strategy=routing_strategy,
                    config=config,
                )

                start_t = time.perf_counter()
                try:
                    simulator.run()
                except Exception:
                    logger.exception("Simulation failed")
                    fail_count += 1
                finally:
                    duration = time.perf_counter() - start_t
                    sample_runtimes.append(duration)

            avg_runtime = mean(sample_runtimes)
            runtimes[strat_name].append(avg_runtime)

            if fail_count == n_samples:
                strategy_dead[strat_name] = True

    plt.figure(figsize=(10, 6))
    for strat_name, rt in runtimes.items():
        plt.plot(n_qubits_list, rt, marker="o", label=strat_name)

    plt.xlabel("Number of Qubits")
    plt.ylabel("Average Runtime per Run [s]")
    plt.title(
        "Runtime vs. Number of Qubits\n"
        "3x3 Grid, RandomPlacement, "
        f"p_success={p_success}, p_repair={p_repair}, {n_samples} Samples"
    )
    plt.xticks(n_qubits_list, rotation=45)
    plt.grid(visible=True, which="both", linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig("D:\\Uni\\runtime_qubits.png")
    plt.show()

    return runtimes


def evaluate_strategy_with_errorbars(
    routing_strategy: RoutingStrategy,
    n_qubits_list: list[int],
    n_samples: int = 20,
    width: int = 3,
    height: int = 3,
    rounds: int = 5,
    p_success: float = 0.99,
    p_repair: float = 0.25,
) -> tuple[list[float], list[float], list[float], list[float], list[int]]:
    placement: PlacementStrategy = RandomPlacementStrategy()

    t_mean: list[float] = []
    t_std: list[float] = []
    m_mean: list[float] = []
    m_std: list[float] = []
    n_success: list[int] = []

    strategy_dead = False

    for n_qubits in n_qubits_list:
        if strategy_dead:
            t_mean.append(float("nan"))
            t_std.append(float("nan"))
            m_mean.append(float("nan"))
            m_std.append(float("nan"))
            n_success.append(0)
            continue

        timesteps_samples: list[int] = []
        movements_samples: list[int] = []

        for sample_idx in range(n_samples):
            base_seed = 1000 * n_qubits + sample_idx
            random.seed(base_seed)

            config = SimulationConfig(
                width=width,
                height=height,
                n_qubits=n_qubits,
                rounds=rounds,
                p_success=p_success,
                p_repair=p_repair,
                seed=base_seed,
            )

            simulator = RoutingSimulator(
                placement_strategy=placement,
                routing_strategy=routing_strategy,
                config=config,
            )

            try:
                timelines, _ = simulator.run()
            except Exception:
                logger.exception("Simulation failed")
                continue

            timesteps_samples.append(total_timesteps(timelines))
            movements_samples.append(count_movements(timelines))

        n_success.append(len(timesteps_samples))

        if timesteps_samples:
            t_mean.append(mean(timesteps_samples))
            m_mean.append(mean(movements_samples))

            t_std.append(stdev(timesteps_samples) if len(timesteps_samples) > 1 else 0.0)
            m_std.append(stdev(movements_samples) if len(movements_samples) > 1 else 0.0)
        else:
            t_mean.append(float("nan"))
            t_std.append(float("nan"))
            m_mean.append(float("nan"))
            m_std.append(float("nan"))
            strategy_dead = True

    return t_mean, t_std, m_mean, m_std, n_success


def save_results_csv(
    path: str,
    n_qubits_list: list[int],
    strategy_name: str,
    timesteps_mean: list[float],
    timesteps_std: list[float],
    movements_mean: list[float],
    movements_std: list[float],
    n_success: list[int],
    n_samples: int,
) -> None:
    pathlib.Path(pathlib.Path(path).parent or ".").mkdir(exist_ok=True, parents=True)

    file_exists = pathlib.Path(path).exists()
    with pathlib.Path(path).open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "strategy",
                "n_qubits",
                "timesteps_mean",
                "timesteps_std",
                "movements_mean",
                "movements_std",
                "n_success",
                "n_samples",
            ])
        for i, nq in enumerate(n_qubits_list):
            writer.writerow([
                strategy_name,
                nq,
                timesteps_mean[i],
                timesteps_std[i],
                movements_mean[i],
                movements_std[i],
                n_success[i],
                n_samples,
            ])


def load_results_csv(path: str) -> dict[str, dict[int, dict[str, float]]]:
    data: dict[str, dict[int, dict[str, float]]] = {}
    if not pathlib.Path(path).exists():
        return data

    with pathlib.Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            strat = row["strategy"]
            nq = int(row["n_qubits"])
            data.setdefault(strat, {})
            data[strat][nq] = {
                "timesteps_mean": float(row["timesteps_mean"]),
                "timesteps_std": float(row["timesteps_std"]),
                "movements_mean": float(row["movements_mean"]),
                "movements_std": float(row["movements_std"]),
                "n_success": int(float(row["n_success"])),
                "n_samples": int(float(row["n_samples"])),
            }
    return data


def plot_two_axis_with_errorbars(
    n_qubits_list: list[int],
    results: dict[str, dict[int, dict[str, float]]],
    out_png: str,
    title: str,
) -> None:
    with plt.style.context(["science", "nature"]):
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax2 = ax1.twinx()

        for strat_name, per_nq in results.items():
            x = np.array(n_qubits_list, dtype=float)

            t_mean = np.array([per_nq.get(nq, {}).get("timesteps_mean", np.nan) for nq in n_qubits_list], dtype=float)
            t_std = np.array([per_nq.get(nq, {}).get("timesteps_std", np.nan) for nq in n_qubits_list], dtype=float)

            m_mean = np.array([per_nq.get(nq, {}).get("movements_mean", np.nan) for nq in n_qubits_list], dtype=float)
            m_std = np.array([per_nq.get(nq, {}).get("movements_std", np.nan) for nq in n_qubits_list], dtype=float)

            ax1.errorbar(
                x,
                t_mean,
                yerr=t_std,
                marker="o",
                linestyle="-",
                capsize=3,
                label=f"{strat_name} (timesteps)",
            )

            ax2.errorbar(
                x,
                m_mean,
                yerr=m_std,
                marker="s",
                linestyle="--",
                capsize=3,
                label=f"{strat_name} (movements)",
            )

        ax1.set_xlabel("Number of Qubits")
        ax1.set_ylabel("Timesteps")
        ax2.set_ylabel("Movements")

        ax1.set_title(title)
        ax1.set_xticks(n_qubits_list)
        ax1.grid(visible=True, which="both", linestyle="--", alpha=0.4)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        legend = ax1.legend(
            h1 + h2,
            l1 + l2,
            loc="best",
            frameon=True,
        )
        legend.get_frame().set_facecolor("white")
        legend.get_frame().set_edgecolor("black")
        legend.get_frame().set_alpha(1.0)

        fig.tight_layout()
        fig.savefig(out_png, dpi=300)
        plt.show()


def plot_two_axis_no_errorbars(
    n_qubits_list: list[int],
    results: dict[str, dict[int, dict[str, float]]],
    out_png: str,
    title: str,
) -> None:
    with plt.style.context(["science", "nature"]):
        plt.rcParams.update({
            "font.size": 14,
            "axes.labelsize": 13,
            "axes.titlesize": 12,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
        })
        fig, ax1 = plt.subplots(figsize=(8, 4))
        ax2 = ax1.twinx()

        for strat_name, per_nq in results.items():
            x = np.array(n_qubits_list, dtype=float)

            t_mean = np.array(
                [per_nq.get(nq, {}).get("timesteps_mean", np.nan) for nq in n_qubits_list],
                dtype=float,
            )
            m_mean = np.array(
                [per_nq.get(nq, {}).get("movements_mean", np.nan) for nq in n_qubits_list],
                dtype=float,
            )

            ax1.plot(
                x,
                t_mean,
                marker="o",
                linestyle="-",
                color="#ed9015" if strat_name == "Rotation Algorithm with Waiting" else "tab:blue",
                label=f"{strat_name} (Timesteps)",
            )

            ax2.plot(
                x,
                m_mean,
                marker="s",
                linestyle="--",
                color="#ed9015" if strat_name == "Rotation Algorithm with Waiting" else "tab:blue",
                label=f"{strat_name} (Movements)",
            )

        ax1.set_xlabel("Number of Qubits", labelpad=6)
        ax1.set_ylabel("Mean Timesteps (solid)", labelpad=8)
        ax2.set_ylabel("Mean Movements (dashed)", labelpad=8)

        ax1.set_title(title)
        ax1.set_xticks(n_qubits_list)
        ax1.grid(visible=True, which="both", linestyle="--", alpha=0.4)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        legend = ax1.legend(
            h1 + h2,
            l1 + l2,
            loc="best",
            borderaxespad=0.7,
            borderpad=0.5,
            frameon=True,
        )
        legend.get_frame().set_facecolor("white")
        legend.get_frame().set_edgecolor("black")
        legend.get_frame().set_alpha(1.0)

        fig.tight_layout()
        fig.savefig(out_png, dpi=300)
        plt.show()


def main() -> None:
    width, height = 3, 3
    rounds = 5
    p_success = 0.99
    p_repair = 0.25
    n_samples = 50

    n_qubits_list = list(range(2, 25))

    csv_path = "results_strategy_3x3.csv"
    plot_path = "strategy_3x3_timesteps_movements.pdf"

    existing = load_results_csv(csv_path)

    strategies = {
        "Default": DefaultRoutingPlanner(),
        "Rotation": RotationRoutingPlanner(),
    }

    for strat_name, strat in strategies.items():
        missing_any = strat_name not in existing or any(nq not in existing[strat_name] for nq in n_qubits_list)
        if missing_any:
            already = existing.get(strat_name, {})
            todo_nqs = [nq for nq in n_qubits_list if nq not in already]
            if not todo_nqs:
                continue

            t_mean, t_std, m_mean, m_std, n_success = evaluate_strategy_with_errorbars(
                routing_strategy=strat,
                n_qubits_list=todo_nqs,
                n_samples=n_samples,
                width=width,
                height=height,
                rounds=rounds,
                p_success=p_success,
                p_repair=p_repair,
            )

            save_results_csv(
                path=csv_path,
                n_qubits_list=todo_nqs,
                strategy_name=strat_name,
                timesteps_mean=t_mean,
                timesteps_std=t_std,
                movements_mean=m_mean,
                movements_std=m_std,
                n_success=n_success,
                n_samples=n_samples,
            )

            existing = load_results_csv(csv_path)

    plot_two_axis_no_errorbars(
        n_qubits_list=n_qubits_list,
        results={
            "Path Algorithm with Waiting": existing.get("Default", {}),
            "Rotation Algorithm with Waiting": existing.get("Rotation", {}),
        },
        out_png=plot_path,
        title="",
    )


if __name__ == "__main__":
    main()
