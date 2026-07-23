from __future__ import annotations

import random

from placements.placement_strategy import PlacementStrategy


class RandomPlacementStrategy(PlacementStrategy):
    def place_qubits(
        self,
        sn_nodes: list[tuple[int, int]],
        n_qubits: int,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        return random.Random(seed).sample(sn_nodes, n_qubits)