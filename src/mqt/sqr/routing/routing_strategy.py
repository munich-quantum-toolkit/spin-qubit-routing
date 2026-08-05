from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeAlias

import networkx as nx

from mqt.sqr.routing.common import Coord, Qubit, TimedNode


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
        G: nx.Graph,
        qubits: list[Qubit],
        pairs: list[QubitPair],
        p_success: float,
        p_repair: float,
    ) -> RoutingResult:
        ...
