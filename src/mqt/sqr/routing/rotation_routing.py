# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

from mqt.sqr.routing.default_routing import DefaultRoutingPlanner
from mqt.sqr.routing.routing_strategy import RoutingResult, RoutingStrategy

if TYPE_CHECKING:
    from mqt.sqr.routing.common import Coord, Qubit, TimedNode

MAX_WAIT_TIME = 100


class RotationRoutingPlanner(RoutingStrategy):
    def route(
        self,
        graph: nx.Graph,
        qubits: list[Qubit],
        pairs: list[tuple[Qubit, Qubit]],
        p_success: float,
        p_repair: float,
    ) -> RoutingResult:
        rt = RouteRuntime(graph, qubits, p_success, p_repair)

        live_pre_by_pair: dict[tuple[int, int], dict[int, Coord]] = {}
        pair_order: dict[tuple[int, int], int] = {(qa.id, qb.id): index for index, (qa, qb) in enumerate(pairs)}
        remaining: set[tuple[int, int]] = {(qa.id, qb.id) for qa, qb in pairs}

        while remaining:
            ready = [pid for pid in remaining if is_ready_pair(pid, remaining, pair_order)]
            if not ready:
                ready = list(remaining)

            plans: dict[tuple[int, int], SoloPlan] = {}
            sequential_fallback: list[tuple[int, int]] = []

            for pid in sorted(ready, key=lambda p: pair_order[p]):
                a, b = pid
                plan = self._plan_pair_solo(rt, a, b)
                if plan is None:
                    sequential_fallback.append(pid)
                else:
                    plans[pid] = plan

            if not plans and not sequential_fallback:
                rt.commit_tick({}, sample=True)
                break

            groups = group_parallel(plans) if plans else []
            finished = False

            for grp in groups:
                group_qids: set[int] = {x for ab in grp for x in ab}
                length = max(plans[pid].length for pid in grp) if grp else 0

                parallel_failed = False
                step = 0
                while step < length:
                    updates_pair_only: dict[int, Coord] = {}
                    sample_flags: list[bool] = []
                    step_diamonds: list[tuple[list[Coord], int]] = []
                    pending_live_pre: dict[tuple[int, int], dict[int, Coord]] = {}

                    for pid in grp:
                        plan = plans[pid]
                        s = plan.ticks[step] if step < plan.length else SoloStep({}, [], sample=True)

                        if plan.in_idx is not None and step == plan.in_idx:
                            a_id, b_id = pid
                            pending_live_pre[pid] = {
                                a_id: rt.current_pos[a_id],
                                b_id: rt.current_pos[b_id],
                            }

                        if plan.out_idx is not None and step == plan.out_idx:
                            a_id, b_id = pid
                            pre_map = live_pre_by_pair.get(
                                pid,
                                {
                                    a_id: rt.current_pos[a_id],
                                    b_id: rt.current_pos[b_id],
                                },
                            )
                            s = SoloStep({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

                        if set(updates_pair_only.keys()) & set(s.updates_pair_only.keys()):
                            parallel_failed = True
                            break

                        updates_pair_only.update(s.updates_pair_only)
                        sample_flags.append(s.sample)
                        step_diamonds.extend(s.diamonds)

                    if parallel_failed:
                        break

                    if foreign_qubits_on_any_diamond(
                        rt.current_pos,
                        step_diamonds,
                        allowed=group_qids,
                    ):
                        parallel_failed = True
                        break

                    updates = expand_runtime_rotations(rt.current_pos, updates_pair_only, step_diamonds)
                    do_sample = False not in sample_flags

                    moved = rt.commit_tick(updates, sample=do_sample)
                    if moved:
                        live_pre_by_pair.update(dict(pending_live_pre.items()))
                        step += 1
                    else:
                        continue

                if parallel_failed:
                    for pid in grp:
                        plan = plans[pid]
                        a_id, b_id = pid
                        step = 0
                        while step < plan.length:
                            s = plan.ticks[step]
                            pending_pre: dict[int, Coord] | None = None

                            if plan.in_idx is not None and step == plan.in_idx:
                                pending_pre = {
                                    a_id: rt.current_pos[a_id],
                                    b_id: rt.current_pos[b_id],
                                }

                            if plan.out_idx is not None and step == plan.out_idx:
                                pre_map = live_pre_by_pair.get(
                                    pid,
                                    {
                                        a_id: rt.current_pos[a_id],
                                        b_id: rt.current_pos[b_id],
                                    },
                                )
                                s = SoloStep({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

                            updates = expand_runtime_rotations(rt.current_pos, s.updates_pair_only, s.diamonds)
                            moved = rt.commit_tick(updates, sample=s.sample)
                            if moved:
                                if pending_pre is not None:
                                    live_pre_by_pair[pid] = pending_pre
                                step += 1
                            else:
                                continue

                remaining.difference_update(grp)

                finished = True
                break

            if finished:
                continue

            if sequential_fallback:
                pid = sequential_fallback[0]
                a, b = pid
                plan = self._plan_pair_solo(rt, a, b)

                if plan is None:
                    rt.commit_tick({}, sample=False)
                else:
                    step = 0
                    while step < plan.length:
                        s = plan.ticks[step]
                        pending_pre: dict[int, Coord] | None = None

                        if plan.in_idx is not None and step == plan.in_idx:
                            pending_pre = {a: rt.current_pos[a], b: rt.current_pos[b]}

                        if plan.out_idx is not None and step == plan.out_idx:
                            pre_map = live_pre_by_pair.get(
                                pid,
                                {a: rt.current_pos[a], b: rt.current_pos[b]},
                            )
                            s = SoloStep({a: pre_map[a], b: pre_map[b]}, [], sample=False)

                        updates = expand_runtime_rotations(rt.current_pos, s.updates_pair_only, s.diamonds)
                        moved = rt.commit_tick(updates, sample=s.sample)
                        if moved:
                            if pending_pre is not None:
                                live_pre_by_pair[pid] = pending_pre
                            step += 1
                        else:
                            continue

                remaining.discard(pid)
            else:
                rt.commit_tick({}, sample=True)

        return rt.timelines, rt.edge_timebands

    def _plan_pair_solo(self, rt: RouteRuntime, id_a: int, id_b: int) -> SoloPlan | None:
        la = rt.current_pos[id_a]
        lb = rt.current_pos[id_b]
        if not (is_sn(rt.graph, la) and is_sn(rt.graph, lb)):
            return None

        ticks: list[SoloStep] = []
        trace: dict[int, list[Coord]] = {id_a: [la], id_b: [lb]}
        used_diamonds: set[tuple[Coord, Coord, Coord, Coord]] = set()
        in_idx: int | None = None
        out_idx: int | None = None

        cands = DefaultRoutingPlanner.best_meeting_candidates(rt.graph, la, lb, reserved=set(), forbidden_nodes=set())

        best_choice: tuple[Coord, tuple[Coord, list[Coord]], tuple[Coord, list[Coord]]] | None = None
        for meet in cands:
            if not is_in(rt.graph, meet):
                continue

            pa = self._best_pre(rt, meet, la)
            pb = self._best_pre(rt, meet, lb)
            if pa and pb:
                best_choice = (meet, pa, pb)
                break

        if best_choice is None:
            return None

        meet, (pre_a, path_a), (pre_b, path_b) = best_choice
        idx_a = 0
        idx_b = 0

        while la != pre_a or lb != pre_b:
            updates: dict[int, Coord] = {}
            diamonds_for_step: list[tuple[list[Coord], int]] = []

            if la != pre_a and idx_a + 1 < len(path_a):
                u_a, v_a = path_a[idx_a], path_a[idx_a + 1]
                if is_diag(u_a, v_a):
                    d_a = diamond_for_edge(rt.graph, u_a, v_a)
                    if d_a:
                        dir_a = rot_dir(d_a, u_a, v_a)
                        upd_a = compute_pair_rotation_updates_for_diamond(d_a, dir_a, id_a, id_b, la, lb)
                        upd_a[id_a] = v_a
                        updates.update(upd_a)
                        diamonds_for_step.append((d_a, dir_a))
                        used_diamonds.add(canonical_diamond_tuple(d_a))
                    else:
                        updates[id_a] = v_a
                else:
                    updates[id_a] = v_a

            if lb != pre_b and idx_b + 1 < len(path_b):
                u_b, v_b = path_b[idx_b], path_b[idx_b + 1]
                if is_diag(u_b, v_b):
                    d_b = diamond_for_edge(rt.graph, u_b, v_b)
                    if d_b:
                        dir_b = rot_dir(d_b, u_b, v_b)
                        upd_b = compute_pair_rotation_updates_for_diamond(d_b, dir_b, id_a, id_b, la, lb)
                        upd_b[id_b] = v_b
                        overlaps_existing = diamonds_for_step and set(diamonds_for_step[0][0]).intersection(d_b)
                        if not overlaps_existing:
                            updates.update(upd_b)
                            diamonds_for_step.append((d_b, dir_b))
                            used_diamonds.add(canonical_diamond_tuple(d_b))
                    elif id_b not in updates:
                        updates[id_b] = v_b
                elif id_b not in updates:
                    updates[id_b] = v_b

            if not updates:
                return None

            la = updates.get(id_a, la)
            lb = updates.get(id_b, lb)
            if id_a in updates:
                idx_a = min(idx_a + 1, len(path_a) - 1)
            if id_b in updates:
                idx_b = min(idx_b + 1, len(path_b) - 1)

            ticks.append(
                SoloStep(
                    updates_pair_only=updates,
                    sample=True,
                    diamonds=diamonds_for_step,
                )
            )
            trace[id_a].append(la)
            trace[id_b].append(lb)

        updates_in: dict[int, Coord] = {}
        if la != meet:
            updates_in[id_a] = meet
        if lb != meet:
            updates_in[id_b] = meet

        if updates_in:
            la = updates_in.get(id_a, la)
            lb = updates_in.get(id_b, lb)
            in_idx = len(ticks)
            ticks.append(SoloStep(updates_pair_only=updates_in, diamonds=[], sample=True))
            trace[id_a].append(la)
            trace[id_b].append(lb)

        out_idx = len(ticks)
        ticks.append(SoloStep(updates_pair_only={}, diamonds=[], sample=False))
        trace[id_a].append(pre_a)
        trace[id_b].append(pre_b)

        return SoloPlan(
            ticks=ticks,
            pos_trace=trace,
            used_diamonds=used_diamonds,
            in_idx=in_idx,
            out_idx=out_idx,
        )

    @staticmethod
    def _best_pre(
        rt: RouteRuntime,
        meet: Coord,
        src: Coord,
    ) -> tuple[Coord, list[Coord]] | None:
        best: tuple[Coord, list[Coord]] | None = None
        for pre in sn_neighbors_of_meet(rt.graph, meet):
            p = shortest_path_sn(rt.SN, src, pre)
            if p is None:
                continue
            if best is None or len(p) < len(best[1]):
                best = (pre, p)
        return best


def chebyshev(p: Coord, q: Coord) -> int:
    return max(abs(p[0] - q[0]), abs(p[1] - q[1]))


def edgeset(u: Coord, v: Coord) -> frozenset:
    return frozenset({u, v})


def is_sn(graph: nx.Graph, n: Coord) -> bool:
    return graph.nodes[n].get("type") == "SN"


def is_in(graph: nx.Graph, n: Coord) -> bool:
    return graph.nodes[n].get("type") == "IN"


def is_diag(u: Coord, v: Coord) -> bool:
    return abs(u[0] - v[0]) == 1 and abs(u[1] - v[1]) == 1


def canonical_diamond_tuple(diamond: list[Coord]) -> tuple[Coord, Coord, Coord, Coord]:
    return cast("tuple[Coord, Coord, Coord, Coord]", tuple(sorted(diamond)))


def diag_sn_neighbors(graph: nx.Graph, n: Coord) -> list[Coord]:
    if not is_sn(graph, n):
        return []
    return [w for w in graph.neighbors(n) if is_sn(graph, w) and is_diag(n, w)]


def diamond_for_edge(graph: nx.Graph, u: Coord, v: Coord) -> list[Coord] | None:
    if not (is_sn(graph, u) and is_sn(graph, v) and is_diag(u, v)):
        return None
    su = [w for w in diag_sn_neighbors(graph, u) if w != v]
    sv = [x for x in diag_sn_neighbors(graph, v) if x != u]
    for w in su:
        for x in sv:
            if is_diag(w, x):
                return [u, v, x, w]
    return None


def rot_dir(diamond: list[Coord], u: Coord, v: Coord) -> int:
    i = diamond.index(u)
    return 1 if diamond[(i + 1) % 4] == v else -1


def sn_neighbors_of_meet(graph: nx.Graph, meeting: Coord) -> list[Coord]:
    if not is_in(graph, meeting):
        return []
    return [w for w in graph.neighbors(meeting) if is_sn(graph, w)]


def shortest_path_sn(sn: nx.Graph, src: Coord, dst: Coord) -> list[Coord] | None:
    try:
        return nx.shortest_path(sn, src, dst)
    except nx.NetworkXNoPath:
        return None


def compute_pair_rotation_updates_for_diamond(
    diamond: list[Coord],
    direction: int,
    a_id: int,
    b_id: int,
    la: Coord,
    lb: Coord,
) -> dict[int, Coord]:
    idx = {p: i for i, p in enumerate(diamond)}
    out: dict[int, Coord] = {}
    if la in idx:
        out[a_id] = diamond[(idx[la] + direction) % 4]
    if lb in idx:
        out[b_id] = diamond[(idx[lb] + direction) % 4]
    return out


def plans_compatible_distance(
    p1: SoloPlan,
    ab1: tuple[int, int],
    p2: SoloPlan,
    ab2: tuple[int, int],
) -> bool:
    a1, b1 = ab1
    a2, b2 = ab2
    length = max(p1.length, p2.length)

    def pos(plan: SoloPlan, qid: int, i: int) -> Coord:
        trace = plan.pos_trace[qid]
        return trace[i] if i < len(trace) else trace[-1]

    for i in range(length + 1):
        p_a1 = pos(p1, a1, i)
        p_b1 = pos(p1, b1, i)
        p_a2 = pos(p2, a2, i)
        p_b2 = pos(p2, b2, i)
        for u in (p_a1, p_b1):
            for v in (p_a2, p_b2):
                if chebyshev(u, v) < 3:
                    return False
    return True


def plans_compatible_diamonds(p1: SoloPlan, p2: SoloPlan) -> bool:
    length = max(p1.length, p2.length)
    for i in range(length):
        d1 = {canonical_diamond_tuple(D) for (D, _dir) in p1.ticks[i].diamonds} if i < p1.length else set()
        d2 = {canonical_diamond_tuple(D) for (D, _dir) in p2.ticks[i].diamonds} if i < p2.length else set()
        if not d1.isdisjoint(d2):
            return False
    return True


def group_parallel(plans: dict[tuple[int, int], SoloPlan]) -> list[list[tuple[int, int]]]:
    remaining = sorted(plans.keys())
    groups: list[list[tuple[int, int]]] = []
    used: set[tuple[int, int]] = set()

    for pid in remaining:
        if pid in used:
            continue
        grp = [pid]
        used.add(pid)
        for qid in remaining:
            if qid in used:
                continue
            ok = all(
                plans_compatible_distance(plans[p0], p0, plans[qid], qid)
                and plans_compatible_diamonds(plans[p0], plans[qid])
                for p0 in grp
            )
            if ok:
                grp.append(qid)
                used.add(qid)
        groups.append(grp)

    return groups


def expand_runtime_rotations(
    current_pos: dict[int, Coord],
    base_updates: dict[int, Coord],
    diamonds: list[tuple[list[Coord], int]],
    exclude_qids: set[int] | None = None,
) -> dict[int, Coord]:
    if not diamonds:
        return dict(base_updates)

    exclude_qids = exclude_qids or set()
    idx_cache: dict[tuple[Coord, ...], dict[Coord, int]] = {}
    out = dict(base_updates)

    for diamond, direction in diamonds:
        key = tuple(diamond)
        if key not in idx_cache:
            idx_cache[key] = {p: i for i, p in enumerate(diamond)}
        idx = idx_cache[key]
        for qid, pos in current_pos.items():
            if qid in exclude_qids:
                continue
            if pos in idx:
                out[qid] = diamond[(idx[pos] + direction) % 4]

    return out


def foreign_qubits_on_any_diamond(
    current_pos: dict[int, Coord],
    diamonds: list[tuple[list[Coord], int]],
    allowed: set[int],
) -> bool:
    if not diamonds:
        return False
    nodes: set[Coord] = set()
    for diamond, _ in diamonds:
        nodes |= set(diamond)
    for qid, pos in current_pos.items():
        if qid in allowed:
            continue
        if pos in nodes:
            return True
    return False


def is_ready_pair(
    pid: tuple[int, int],
    remaining: set[tuple[int, int]],
    pair_order: dict[tuple[int, int], int],
) -> bool:
    idx = pair_order[pid]
    a, b = pid
    for other in remaining:
        if other == pid:
            continue
        if pair_order[other] >= idx:
            continue
        x, y = other
        if x in {a, b} or y in {a, b}:
            return False
    return True


@dataclass(frozen=True)
class SoloStep:
    updates_pair_only: dict[int, Coord]
    diamonds: list[tuple[list[Coord], int]]
    sample: bool


class SoloPlan:
    def __init__(
        self,
        ticks: list[SoloStep],
        pos_trace: dict[int, list[Coord]],
        used_diamonds: set[tuple[Coord, Coord, Coord, Coord]],
        in_idx: int | None,
        out_idx: int | None,
    ) -> None:
        self.ticks = ticks
        self.pos_trace = pos_trace
        self.used_diamonds = used_diamonds
        self.in_idx = in_idx
        self.out_idx = out_idx

    @property
    def length(self) -> int:
        return len(self.ticks)


class RouteRuntime:
    def __init__(
        self,
        graph: nx.Graph,
        qubits: list[Qubit],
        p_success: float,
        p_repair: float,
    ) -> None:
        self.graph = graph
        self.p_success = p_success
        self.p_repair = p_repair

        self.current_pos: dict[int, Coord] = {q.id: q.pos for q in qubits}
        self.all_qids: set[int] = {q.id for q in qubits}

        self.timelines: dict[int, list[TimedNode]] = {q.id: [(q.pos, 0)] for q in qubits}
        self.t = 0
        self.wait_streak = 0

        self.defective_edges: set[frozenset] = set()
        self.edge_timebands: list[tuple[int, int, set[frozenset]]] = []

        sn_nodes = [n for n in graph.nodes() if is_sn(graph, n)]
        self.SN = graph.subgraph(sn_nodes).copy()

    def sample_edge_failures(self) -> None:
        for u, v in self.graph.edges():
            e = edgeset(u, v)
            if e in self.defective_edges:
                if random.random() < self.p_repair:
                    self.defective_edges.discard(e)
            elif random.random() < (1.0 - self.p_success):
                self.defective_edges.add(e)

    def would_use_defect(self, pending: dict[int, Coord]) -> bool:
        for qid, newp in pending.items():
            u = self.current_pos[qid]
            v = newp
            if u != v and edgeset(u, v) in self.defective_edges:
                return True
        return False

    def commit_tick(self, pending: dict[int, Coord], *, sample: bool) -> bool:
        if sample:
            self.sample_edge_failures()

        moved = False
        if pending and not self.would_use_defect(pending):
            for qid, newp in pending.items():
                self.current_pos[qid] = newp
            moved = True

        self.wait_streak = 0 if moved else (self.wait_streak + 1)

        self.t += 1
        for qid in self.all_qids:
            last = self.timelines[qid][-1]
            cur = (self.current_pos[qid], self.t)
            if last != cur:
                self.timelines[qid].append(cur)

        self.edge_timebands.append((self.t - 1, self.t, set(self.defective_edges)))

        if self.wait_streak >= MAX_WAIT_TIME:
            msg = f"Routing stuck: {self.wait_streak} consecutive timesteps without movement (t={self.t})."
            raise RuntimeError(msg)

        return moved
