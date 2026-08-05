# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random

from mqt.sqr.placements.placement_strategy import PlacementStrategy


class RandomPlacementStrategy(PlacementStrategy):
    def place_qubits(
        self,
        sn_nodes: list[tuple[int, int]],
        n_qubits: int,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        return random.Random(seed).sample(sn_nodes, n_qubits)
