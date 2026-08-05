# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeAlias

from mqt.sqr.routing.common import Coord, Qubit, TimedNode

if TYPE_CHECKING:
    import networkx as nx

QubitPair: TypeAlias = tuple[Qubit, Qubit]
DefectiveEdge: TypeAlias = frozenset[Coord]
DefectTimeBand: TypeAlias = tuple[int, int, set[DefectiveEdge]]
RoutingResult: TypeAlias = tuple[
    dict[int, list[TimedNode]],
    list[DefectTimeBand],
]


class RoutingStrategy(ABC):
    @abstractmethod
    def route(
        self,
        graph: nx.Graph,
        qubits: list[Qubit],
        pairs: list[QubitPair],
        p_success: float,
        p_repair: float,
    ) -> RoutingResult: ...
