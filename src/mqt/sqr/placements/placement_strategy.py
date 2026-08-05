# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from itertools import starmap
from typing import TYPE_CHECKING

from mqt.sqr.routing.common import Qubit
from mqt.sqr.utils.network import NetworkBuilder

if TYPE_CHECKING:
    import networkx as nx


class PlacementStrategy(ABC):
    def build_pairs(
        self,
        n_qubits: int,
        rounds: int,
        max_pairs_per_round: int | None = None,
        seed: int | None = None,
    ) -> list[tuple[int, int]]:
        rng = random.Random(seed)
        pair_ids: list[tuple[int, int]] = []

        for _ in range(rounds):
            qubit_ids = list(range(n_qubits))
            rng.shuffle(qubit_ids)

            possible_pair_count = len(qubit_ids) // 2
            pair_count = (
                possible_pair_count if max_pairs_per_round is None else min(max_pairs_per_round, possible_pair_count)
            )

            for pair_index in range(pair_count):
                first_id = qubit_ids[2 * pair_index]
                second_id = qubit_ids[2 * pair_index + 1]
                pair_ids.append((first_id, second_id))

        return pair_ids

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

        chosen_coordinates = self.place_qubits(
            sn_nodes=sn_nodes,
            n_qubits=n_qubits,
            seed=seed,
        )

        qubits = list(starmap(Qubit, enumerate(chosen_coordinates)))
        qubits_by_id = {qubit.id: qubit for qubit in qubits}

        pairs = [(qubits_by_id[first_id], qubits_by_id[second_id]) for first_id, second_id in pair_ids]

        return network, qubits, pairs

    @abstractmethod
    def place_qubits(
        self,
        sn_nodes: list[tuple[int, int]],
        n_qubits: int,
        seed: int | None = None,
    ) -> list[tuple[int, int]]: ...
