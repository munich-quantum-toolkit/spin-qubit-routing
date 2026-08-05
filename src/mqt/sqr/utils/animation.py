# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

Coord: TypeAlias = tuple[int, int]
Position: TypeAlias = tuple[float, float]
TimedNode: TypeAlias = tuple[Coord, int]
Edge: TypeAlias = frozenset[Coord]
EdgeTimeBand: TypeAlias = tuple[int, int, set[Edge]]
AgentId: TypeAlias = Hashable

NODE_SIZE = 120

AGENT_COLORS = (
    "tab:red",
    "tab:green",
    "tab:orange",
    "tab:purple",
    "tab:brown",
    "tab:pink",
    "tab:gray",
    "tab:olive",
    "tab:cyan",
)


@dataclass(frozen=True)
class AgentAnimationData:
    agent_id: AgentId
    color: str
    positions: list[Position]
    frames: list[float]
    last_index: int
    frame_to_position: dict[float, Position]
    first_frame: float | None
    last_frame: float | None


def _build_time_indexed_positions(
    path: Sequence[TimedNode],
) -> tuple[dict[int, Coord], int, int]:
    if not path:
        return {}, 0, 0

    start_time = path[0][1]
    end_time = path[-1][1]
    positions_by_time: dict[int, Coord] = {}
    path_index = 0

    for time in range(start_time, end_time + 1):
        while path_index + 1 < len(path) and path[path_index + 1][1] <= time:
            path_index += 1

        positions_by_time[time] = path[path_index][0]

    return positions_by_time, start_time, end_time


def _interpolate(
    start: Coord,
    end: Coord,
    alpha: float,
) -> Position:
    return (
        start[0] + (end[0] - start[0]) * alpha,
        start[1] + (end[1] - start[1]) * alpha,
    )


def _make_smooth_positions(
    path: Sequence[TimedNode],
    substeps: int = 5,
) -> tuple[list[Position], list[float], int]:
    if not path:
        return [], [], -1

    positions_by_time, start_time, end_time = _build_time_indexed_positions(path)
    positions: list[Position] = []
    frames: list[float] = []

    for time in range(start_time, end_time):
        start = positions_by_time[time]
        end = positions_by_time[time + 1]

        for substep in range(substeps):
            alpha = substep / float(substeps)
            positions.append(_interpolate(start, end, alpha))
            frames.append(time + alpha)

    final_position = positions_by_time[end_time]
    positions.append(final_position)
    frames.append(float(end_time))

    return positions, frames, len(positions) - 1


def _make_step_positions(
    path: Sequence[TimedNode],
) -> tuple[list[Position], list[float], int]:
    if not path:
        return [], [], -1

    positions_by_time, start_time, end_time = _build_time_indexed_positions(path)
    frames = list(range(start_time, end_time + 1))
    positions = [positions_by_time[time] for time in frames]

    return positions, frames, len(positions) - 1


def _agent_sort_key(agent_id: AgentId) -> tuple[int, int | str]:
    value = str(agent_id)

    if value.lstrip("-").isdigit():
        return 0, int(value)

    return 1, value


def animate_mapf(
    G: nx.Graph,
    plans: Mapping[AgentId, Sequence[TimedNode]],
    interval_ms: float = 0.1,
    smooth: bool = True,
    substeps: int = 200,
    edge_timebands: Sequence[EdgeTimeBand] | None = None,
    failed_edges_timeline: Mapping[int, set[Edge]] | None = None,
) -> FuncAnimation:
    graph_positions = {node: node for node in G}

    figure, axis = plt.subplots(
        figsize=(8, 8),
        constrained_layout=True,
    )

    all_segments = [(graph_positions[source], graph_positions[target]) for source, target in G.edges]
    base_edges = LineCollection(
        all_segments,
        alpha=0.3,
        linewidths=1.0,
        zorder=1,
    )
    axis.add_collection(base_edges)

    failed_edges = LineCollection(
        [],
        colors="red",
        linewidths=2.2,
        alpha=0.9,
        zorder=3,
    )
    axis.add_collection(failed_edges)

    interaction_nodes = [node for node, data in G.nodes(data=True) if data.get("type") == "IN"]
    storage_nodes = [node for node, data in G.nodes(data=True) if data.get("type") == "SN"]

    nx.draw_networkx_nodes(
        G,
        graph_positions,
        nodelist=interaction_nodes,
        node_shape="s",
        node_size=NODE_SIZE,
        ax=axis,
    )
    nx.draw_networkx_nodes(
        G,
        graph_positions,
        nodelist=storage_nodes,
        node_shape="o",
        node_size=NODE_SIZE,
        ax=axis,
    )

    axis.set_aspect("equal")
    axis.axis("off")

    agent_ids = sorted(plans, key=_agent_sort_key)
    agent_data: list[AgentAnimationData] = []
    global_frame_set: set[float] = set()

    for index, agent_id in enumerate(agent_ids):
        path = plans[agent_id]

        if smooth:
            positions, frames, last_index = _make_smooth_positions(
                path,
                substeps=substeps,
            )
        else:
            positions, frames, last_index = _make_step_positions(path)

        data = AgentAnimationData(
            agent_id=agent_id,
            color=AGENT_COLORS[index % len(AGENT_COLORS)],
            positions=positions,
            frames=frames,
            last_index=last_index,
            frame_to_position=dict(zip(frames, positions, strict=False)),
            first_frame=frames[0] if frames else None,
            last_frame=frames[-1] if frames else None,
        )
        agent_data.append(data)
        global_frame_set.update(frames)

    global_frames = sorted(global_frame_set)

    moving_artists: list[Line2D] = []
    legend_handles: list[Line2D] = []
    legend_labels: list[str] = []

    for data in agent_data:
        initial_position = data.positions[0] if data.positions else (0.0, 0.0)

        (dot,) = axis.plot(
            [initial_position[0]],
            [initial_position[1]],
            marker="o",
            markersize=8,
            markeredgecolor="black",
            markeredgewidth=1.2,
            linestyle="None",
            color=data.color,
            alpha=0.95,
            zorder=4,
        )
        moving_artists.append(dot)

        legend_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="white",
                markerfacecolor=data.color,
                markeredgecolor="black",
                markersize=8,
                linestyle="None",
            )
        )
        legend_labels.append(f"Qubit {data.agent_id}")

    axis.legend(
        legend_handles,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=True,
    )

    def get_agent_position(
        data: AgentAnimationData,
        global_frame: float,
    ) -> Position:
        if not data.frames:
            return 0.0, 0.0

        exact_position = data.frame_to_position.get(global_frame)
        if exact_position is not None:
            return exact_position

        if data.first_frame is not None and global_frame < data.first_frame:
            return data.positions[0]

        if data.last_frame is not None and global_frame > data.last_frame:
            return data.positions[-1]

        previous_frame = max(frame for frame in data.frames if frame <= global_frame)
        return data.frame_to_position[previous_frame]

    def get_failed_segments(
        global_frame: float,
    ) -> list[tuple[Coord, Coord]]:
        time = math.floor(global_frame + 1e-9)

        if failed_edges_timeline is not None:
            current_failed_edges = failed_edges_timeline.get(
                time,
                set(),
            )
        elif edge_timebands is not None:
            current_failed_edges: set[Edge] = set()

            for start_time, end_time, edges in edge_timebands:
                if start_time <= time < end_time:
                    current_failed_edges.update(edges)
        else:
            return []

        segments: list[tuple[Coord, Coord]] = []

        for edge in current_failed_edges:
            source, target = tuple(edge)
            segments.append((
                graph_positions[source],
                graph_positions[target],
            ))

        return segments

    def update(frame_index: int) -> list[Line2D | LineCollection]:
        global_frame = global_frames[frame_index]

        failed_edges.set_segments(get_failed_segments(global_frame))

        artists: list[Line2D | LineCollection] = [failed_edges]

        for index, data in enumerate(agent_data):
            x, y = get_agent_position(data, global_frame)
            moving_artists[index].set_data([x], [y])
            artists.append(moving_artists[index])

        return artists

    animation = FuncAnimation(
        figure,
        update,
        frames=len(global_frames),
        interval=interval_ms,
        blit=True,
        repeat=True,
    )

    plt.show()
    return animation
