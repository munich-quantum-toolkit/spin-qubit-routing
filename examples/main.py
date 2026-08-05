# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from mqt.sqr.placements.random_strategy import RandomPlacementStrategy
from mqt.sqr.routing.rotation_routing import RotationRoutingPlanner
from mqt.sqr.simulation import RoutingSimulator, SimulationConfig

if TYPE_CHECKING:
    from mqt.sqr.placements.placement_strategy import PlacementStrategy
    from mqt.sqr.routing.routing_strategy import RoutingStrategy


if __name__ == "__main__":
    placement: PlacementStrategy = RandomPlacementStrategy()
    routing: RoutingStrategy = RotationRoutingPlanner()

    # For defective edges
    random.seed(10)

    config = SimulationConfig(
        width=3,
        height=3,
        n_qubits=8,
        rounds=3,
        p_success=1,
        p_repair=0.05,
        # For Qubit-Placement and interactions
        seed=13,
    )

    simulator = RoutingSimulator(
        placement_strategy=placement,
        routing_strategy=routing,
        config=config,
    )

    simulator.run()
