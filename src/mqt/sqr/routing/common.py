# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    import networkx as nx

Coord: TypeAlias = tuple[int, int]
TimedNode: TypeAlias = tuple[Coord, int]
Edge: TypeAlias = frozenset[Coord]
Cost: TypeAlias = tuple[int, int]
QueueEntry: TypeAlias = tuple[Cost, TimedNode]

MAX_TIME = 300


@dataclass(frozen=True)
class Qubit:
    id: int
    pos: Coord


class Reservations:
    def __init__(
        self,
        G: nx.Graph,
        blocked_edges: set[Edge] | None = None,
    ) -> None:
        self.node_caps: dict[Coord, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.edge_caps: dict[Edge, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.node_type: dict[Coord, str] = {node: G.nodes[node]["type"] for node in G.nodes}
        self.blocked_edges = blocked_edges or set()

    def node_capacity(self, node: Coord) -> int:
        return 2 if self.node_type[node] == "IN" else 1

    def can_occupy(self, node: Coord, time: int) -> bool:
        return self.node_caps[node][time] < self.node_capacity(node)

    def occupy_node(self, node: Coord, time: int) -> None:
        self.node_caps[node][time] += 1

    def can_traverse(
        self,
        source: Coord,
        target: Coord,
        time: int,
    ) -> bool:
        edge = frozenset({source, target})

        if edge in self.blocked_edges:
            return False

        return self.edge_caps[edge][time] == 0

    def traverse_edge(
        self,
        source: Coord,
        target: Coord,
        time: int,
    ) -> None:
        edge = frozenset({source, target})
        self.edge_caps[edge][time] += 1

    def commit(self, path: list[TimedNode]) -> None:
        self.occupy_node(*path[0])

        for (source, time), (target, next_time) in itertools.pairwise(path):
            self.occupy_node(target, next_time)

            if source != target:
                self.traverse_edge(source, target, time)


class AStar:
    @staticmethod
    def search(
        G: nx.Graph,
        start: Coord,
        goal: Coord,
        reservations: Reservations,
    ) -> list[TimedNode] | None:
        def heuristic(node: Coord) -> int:
            return max(
                abs(node[0] - goal[0]),
                abs(node[1] - goal[1]),
            )

        start_state: TimedNode = (start, 0)
        distances: dict[TimedNode, Cost] = {start_state: (0, 0)}
        came_from: dict[TimedNode, TimedNode] = {}

        open_queue: list[QueueEntry] = []
        heappush(
            open_queue,
            ((heuristic(start), 0), start_state),
        )

        while open_queue:
            _, current_state = heappop(open_queue)
            node, time = current_state
            move_cost, time_cost = distances[current_state]

            if node == goal:
                path = [current_state]

                while current_state in came_from:
                    current_state = came_from[current_state]
                    path.append(current_state)

                path.reverse()
                return path

            if time >= MAX_TIME:
                continue

            successors = [(node, time + 1, 0, 1)]
            successors.extend((neighbor, time + 1, 1, 1) for neighbor in G.neighbors(node))

            for next_node, next_time, move_delta, time_delta in successors:
                if not reservations.can_occupy(next_node, next_time):
                    continue

                if next_node != node and not reservations.can_traverse(
                    node,
                    next_node,
                    time,
                ):
                    continue

                next_state = (next_node, next_time)
                next_cost = (
                    move_cost + move_delta,
                    time_cost + time_delta,
                )
                previous_cost = distances.get(next_state)

                if previous_cost is not None and next_cost >= previous_cost:
                    continue

                distances[next_state] = next_cost
                came_from[next_state] = current_state

                estimated_cost = (
                    next_cost[0] + heuristic(next_node),
                    next_cost[1] + heuristic(next_node),
                )
                heappush(
                    open_queue,
                    (estimated_cost, next_state),
                )

        return None
