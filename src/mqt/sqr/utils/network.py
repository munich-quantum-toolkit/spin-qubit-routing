# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

from typing import Final, TypeAlias

import networkx as nx

Coord: TypeAlias = tuple[int, int]

_TILE_POSITIONS: Final[dict[int, Coord]] = {
    0: (-1, 1),
    1: (0, 1),
    2: (1, 1),
    3: (-1, 0),
    4: (1, 0),
    5: (-1, -1),
    6: (0, -1),
    7: (1, -1),
}

_INTERACTION_NODE_IDS: Final[frozenset[int]] = frozenset({0, 2, 5, 7})


class NetworkBuilder:
    @staticmethod
    def build_network(
        width: int,
        height: int,
    ) -> nx.Graph:
        if not (isinstance(width, int) and isinstance(height, int) and width >= 1 and height >= 1):
            msg = "width and height must be integers >= 1"
            raise ValueError(msg)

        graph = nx.Graph()

        for row in range(height):
            for column in range(width):
                x_offset = 2 * column
                y_offset = -2 * row

                for tile_id, (x, y) in _TILE_POSITIONS.items():
                    coordinate = (
                        x + x_offset,
                        y + y_offset,
                    )

                    if coordinate in graph:
                        continue

                    node_type = "IN" if tile_id in _INTERACTION_NODE_IDS else "SN"
                    graph.add_node(
                        coordinate,
                        type=node_type,
                    )

        coordinates = list(graph.nodes)
        coordinate_set = set(coordinates)

        for x, y in coordinates:
            source = (x, y)

            for x_delta in (-1, 0, 1):
                for y_delta in (-1, 0, 1):
                    if x_delta == 0 and y_delta == 0:
                        continue

                    target = (
                        x + x_delta,
                        y + y_delta,
                    )

                    if target in coordinate_set:
                        graph.add_edge(source, target)

        return graph
