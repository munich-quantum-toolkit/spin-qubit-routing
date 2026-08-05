# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mqt.sqr.utils.animation import animate_mapf

if TYPE_CHECKING:
    from mqt.sqr.placements.placement_strategy import PlacementStrategy
    from mqt.sqr.routing.routing_strategy import RoutingStrategy


@dataclass
class SimulationConfig:
    width: int
    height: int
    n_qubits: int
    rounds: int
    p_success: float
    p_repair: float
    seed: int


class RoutingSimulator:
    def __init__(
        self,
        placement_strategy: PlacementStrategy,
        routing_strategy: RoutingStrategy,
        config: SimulationConfig,
    ) -> None:
        self.placement_strategy = placement_strategy
        self.routing_strategy = routing_strategy
        self.config = config

    def run(self):
        G, qubits, pairs = self.placement_strategy.build_network_and_place(
            width=self.config.width,
            height=self.config.height,
            n_qubits=self.config.n_qubits,
            rounds=self.config.rounds,
            seed=self.config.seed,
        )

        # 2) Routing
        timelines, edge_timebands = self.routing_strategy.route(
            G,
            qubits,
            pairs,
            self.config.p_success,
            self.config.p_repair,
        )

        animate_mapf(G, timelines, edge_timebands=edge_timebands, smooth=True)

        return timelines, edge_timebands
