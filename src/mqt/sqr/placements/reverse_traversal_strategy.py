# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from itertools import starmap
from typing import TYPE_CHECKING

from typing_extensions import override

from mqt.sqr.placements.placement_strategy import PlacementStrategy
from mqt.sqr.routing.common import Coord, Qubit
from mqt.sqr.routing.rotation_routing import RotationRoutingPlanner
from mqt.sqr.utils.network import NetworkBuilder

if TYPE_CHECKING:
    import networkx as nx


class ReverseTraversalPlacementStrategy(PlacementStrategy):
    @override
    def place_qubits(
        self,
        sn_nodes: list[tuple[int, int]],
        n_qubits: int,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        return random.Random(seed).sample(sn_nodes, n_qubits)

    def build_network_and_place(
        self,
        width: int,
        height: int,
        n_qubits: int,
        rounds: int,
        max_pairs_per_round: int | None = None,
        seed: int | None = None,
    ) -> tuple[nx.Graph, list[Qubit], list[tuple[Qubit, Qubit]]]:
        pair_ids = self.build_pairs(
            n_qubits=n_qubits,
            rounds=rounds,
            max_pairs_per_round=max_pairs_per_round,
            seed=seed,
        )

        network = NetworkBuilder.build_network(width, height)
        sn_nodes = [node for node, data in network.nodes(data=True) if data.get("type") == "SN"]

        if n_qubits > len(sn_nodes):
            msg = f"n_qubits={n_qubits} exceeds available SN nodes ({len(sn_nodes)})."
            raise ValueError(msg)

        initial_coordinates = random.Random(seed).sample(sn_nodes, n_qubits)
        initial_qubits = list(starmap(Qubit, enumerate(initial_coordinates)))
        initial_qubits_by_id = {qubit.id: qubit for qubit in initial_qubits}

        warmup_pairs = [
            (
                initial_qubits_by_id[first_id],
                initial_qubits_by_id[second_id],
            )
            for first_id, second_id in reversed(pair_ids)
        ]

        router = RotationRoutingPlanner()
        timelines, _ = router.route(
            network,
            initial_qubits,
            warmup_pairs,
            p_success=1.0,
            p_repair=1.0,
        )

        final_coordinates_by_id: dict[int, Coord] = {
            qubit_id: timeline[-1][0] for qubit_id, timeline in timelines.items()
        }

        final_qubits = [Qubit(qubit_id, final_coordinates_by_id[qubit_id]) for qubit_id in range(n_qubits)]
        final_qubits_by_id = {qubit.id: qubit for qubit in final_qubits}

        final_pairs = [
            (
                final_qubits_by_id[first_id],
                final_qubits_by_id[second_id],
            )
            for first_id, second_id in pair_ids
        ]

        return network, final_qubits, final_pairs
