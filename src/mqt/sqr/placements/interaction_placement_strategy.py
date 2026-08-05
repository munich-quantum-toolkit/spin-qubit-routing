# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from typing import Final

import networkx as nx

from mqt.sqr.placements.placement_strategy import PlacementStrategy

DECAY: Final = 0.9


class InteractionPlacementStrategy(PlacementStrategy):
    _last_pair_ids: list[tuple[int, int]] | None = None

    def build_pairs(
        self,
        n_qubits: int,
        rounds: int,
        max_pairs_per_round: int | None = None,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        pair_ids = super().build_pairs(
            n_qubits=n_qubits,
            rounds=rounds,
            max_pairs_per_round=max_pairs_per_round,
            seed=seed,
        )
        self._last_pair_ids = pair_ids
        return pair_ids

    def place_qubits(
        self,
        sn_nodes: list[tuple[int, int]],
        n_qubits: int,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        if self._last_pair_ids is None:
            return random.Random(seed).sample(sn_nodes, n_qubits)

        interaction_weights: dict[tuple[int, int], float] = {}

        for index, (first_id, second_id) in enumerate(self._last_pair_ids):
            if first_id == second_id:
                continue

            interaction = tuple(sorted((first_id, second_id)))
            weight = DECAY**index

            interaction_weights[interaction] = interaction_weights.get(interaction, 0.0) + weight

        interaction_graph = nx.Graph()
        interaction_graph.add_nodes_from(range(n_qubits))

        for (first_id, second_id), weight in interaction_weights.items():
            interaction_graph.add_edge(
                first_id,
                second_id,
                weight=weight,
            )

        positions = nx.spring_layout(
            interaction_graph,
            weight="weight",
            seed=seed,
        )

        def position_key(qubit_id: int) -> tuple[float, float]:
            x, y = positions.get(qubit_id, (0.0, 0.0))
            return float(x), float(y)

        qubit_order = sorted(range(n_qubits), key=position_key)
        sorted_sn_nodes = sorted(sn_nodes, key=lambda coordinate: coordinate)

        if n_qubits > len(sorted_sn_nodes):
            msg = f"n_qubits={n_qubits} exceeds available SN nodes ({len(sorted_sn_nodes)})."
            raise ValueError(msg)

        coordinates_by_qubit_id = {qubit_id: sorted_sn_nodes[index] for index, qubit_id in enumerate(qubit_order)}

        return [coordinates_by_qubit_id[qubit_id] for qubit_id in range(n_qubits)]
