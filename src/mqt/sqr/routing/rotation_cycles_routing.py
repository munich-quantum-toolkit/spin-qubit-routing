# Copyright (c) 2026 Chair for Design Automation, TUM
# All rights reserved.
#
# SPDX-License-Identifier: MIT
#
# Licensed under the MIT License

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx
from typing_extensions import override

from mqt.sqr.routing.default_routing import DefaultRoutingPlanner
from mqt.sqr.routing.routing_strategy import RoutingResult, RoutingStrategy

if TYPE_CHECKING:
    from collections.abc import Callable

    from mqt.sqr.routing.common import Coord, Qubit, TimedNode

MAX_WAIT_TIME = 100


def chebyshev(p: Coord, q: Coord) -> int:
    return max(abs(p[0] - q[0]), abs(p[1] - q[1]))


def _edgeset(u: Coord, v: Coord) -> frozenset:
    return frozenset({u, v})


def _is_diag(u: Coord, v: Coord) -> bool:
    return abs(u[0] - v[0]) == 1 and abs(u[1] - v[1]) == 1


@dataclass(frozen=True)
class _Step:
    updates_pair_only: dict[int, Coord]
    loops: list[tuple[list[Coord], int]]
    sample: bool


@dataclass
class _Plan:
    ticks: list[_Step]
    pos_trace: dict[int, list[Coord]]
    used_loops: set[tuple[Coord, ...]]
    in_idx: int | None
    out_idx: int | None

    @property
    def length(self) -> int:
        return len(self.ticks)


class _RoutingContext:
    def __init__(
        self,
        graph: nx.Graph,
        qubits: list[Qubit],
        p_success: float,
        p_repair: float,
        *,
        max_wait_time: int | None = None,
        stuck_error_prefix: str = "Routing stuck",
    ) -> None:
        self.graph = graph
        self.p_success = p_success
        self.p_repair = p_repair
        self.max_wait_time = max_wait_time
        self.stuck_error_prefix = stuck_error_prefix

        self.current_pos: dict[int, Coord] = {q.id: q.pos for q in qubits}
        self.all_qids: set[int] = {q.id for q in qubits}

        self.timelines: dict[int, list[TimedNode]] = {q.id: [(self.current_pos[q.id], 0)] for q in qubits}
        self.t = 0

        self.defective_edges: set[frozenset] = set()
        self.edge_timebands: list[tuple[int, int, set[frozenset]]] = []

        self.wait_streak = 0 if max_wait_time is not None else None

        sn_nodes = [n for n in self.graph.nodes() if self.is_sn(n)]
        self.SN = self.graph.subgraph(sn_nodes).copy()

    def is_sn(self, n: Coord) -> bool:
        return self.graph.nodes[n].get("type") == "SN"

    def is_in(self, n: Coord) -> bool:
        return self.graph.nodes[n].get("type") == "IN"

    def sn_neighbors_of_meet(self, meeting: Coord) -> list[Coord]:
        if not self.is_in(meeting):
            return []
        return [w for w in self.graph.neighbors(meeting) if self.is_sn(w)]

    def shortest_path_sn(self, src: Coord, dst: Coord) -> list[Coord] | None:
        try:
            return nx.shortest_path(self.SN, src, dst)
        except nx.NetworkXNoPath:
            return None

    def sample_edge_failures(self) -> None:
        for u, v in self.graph.edges():
            e = _edgeset(u, v)
            if e in self.defective_edges:
                if random.random() < self.p_repair:
                    self.defective_edges.discard(e)
            elif random.random() < (1.0 - self.p_success):
                self.defective_edges.add(e)

    def would_use_defect(self, pending: dict[int, Coord]) -> bool:
        for qid, newp in pending.items():
            u = self.current_pos[qid]
            v = newp
            if u != v and _edgeset(u, v) in self.defective_edges:
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

        if self.wait_streak is not None:
            if moved:
                self.wait_streak = 0
            else:
                self.wait_streak += 1

        self.t += 1
        for qid in self.all_qids:
            last = self.timelines[qid][-1]
            cur = (self.current_pos[qid], self.t)
            if last != cur:
                self.timelines[qid].append(cur)

        self.edge_timebands.append((self.t - 1, self.t, set(self.defective_edges)))

        if self.wait_streak is not None and self.max_wait_time is not None and self.wait_streak >= self.max_wait_time:
            msg = (
                f"{self.stuck_error_prefix}: {self.wait_streak} aufeinanderfolgende "
                f"Timesteps ohne Bewegung (t={self.t})."
            )
            raise RuntimeError(msg)

        return moved


class _LoopHelpers:
    @staticmethod
    def canonical_loop_tuple(loop: list[Coord]) -> tuple[Coord, ...]:
        return tuple(sorted(loop))

    @staticmethod
    def rot_dir_loop(loop: list[Coord], u: Coord, v: Coord) -> int:
        i = loop.index(u)
        n = len(loop)
        if loop[(i + 1) % n] == v:
            return +1
        if loop[(i - 1) % n] == v:
            return -1
        msg = f"{u}->{v} ist keine Nachbarschaft im Loop"
        raise ValueError(msg)

    @staticmethod
    def compute_pair_rotation_updates_for_loop(
        loop: list[Coord],
        direction: int,
        a_id: int,
        b_id: int,
        la: Coord,
        lb: Coord,
    ) -> dict[int, Coord]:
        idx = {p: i for i, p in enumerate(loop)}
        out: dict[int, Coord] = {}
        n = len(loop)
        if la in idx:
            out[a_id] = loop[(idx[la] + direction) % n]
        if lb in idx:
            out[b_id] = loop[(idx[lb] + direction) % n]
        return out


class _DiamondHelpers:
    @staticmethod
    def diag_sn_neighbors(graph: nx.Graph, is_sn_fn: Callable[[Coord], bool], n: Coord) -> list[Coord]:
        if not is_sn_fn(n):
            return []
        return [w for w in graph.neighbors(n) if is_sn_fn(w) and _is_diag(n, w)]

    @staticmethod
    def diamond_for_edge(graph: nx.Graph, is_sn_fn: Callable[[Coord], bool], u: Coord, v: Coord) -> list[Coord] | None:
        if not (is_sn_fn(u) and is_sn_fn(v) and _is_diag(u, v)):
            return None
        s_u = [w for w in _DiamondHelpers.diag_sn_neighbors(graph, is_sn_fn, u) if w != v]
        s_v = [x for x in _DiamondHelpers.diag_sn_neighbors(graph, is_sn_fn, v) if x != u]
        for w in s_u:
            for x in s_v:
                if _is_diag(w, x):
                    return [u, v, x, w]
        return None

    @staticmethod
    def rot_dir_diamond(diamond: list[Coord], u: Coord, v: Coord) -> int:
        i = diamond.index(u)
        return +1 if diamond[(i + 1) % 4] == v else -1

    @staticmethod
    def canonical_diamond_tuple(diamond: list[Coord]) -> tuple[Coord, Coord, Coord, Coord]:
        return cast("tuple[Coord, Coord, Coord, Coord]", tuple(sorted(diamond)))

    @staticmethod
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


class _PlannerCommon:
    def __init__(self, ctx: _RoutingContext) -> None:
        self.ctx = ctx
        self.live_pre_by_pair: dict[tuple[int, int], dict[int, Coord]] = {}

    def expand_runtime_rotations(
        self,
        base_updates: dict[int, Coord],
        loops: list[tuple[list[Coord], int]],
        *,
        exclude_qids: set[int] | None = None,
    ) -> dict[int, Coord]:
        if not loops:
            return dict(base_updates)

        exclude = exclude_qids or set()
        idx_cache: dict[tuple[Coord, ...], dict[Coord, int]] = {}
        out = dict(base_updates)

        for nodes, direction in loops:
            key = tuple(nodes)
            if key not in idx_cache:
                idx_cache[key] = {p: i for i, p in enumerate(nodes)}
            idx = idx_cache[key]
            n = len(nodes)
            for qid, pos in self.ctx.current_pos.items():
                if qid in exclude:
                    continue
                if pos in idx:
                    out[qid] = nodes[(idx[pos] + direction) % n]

        return out

    def foreign_qubits_on_any_loop(
        self,
        loops: list[tuple[list[Coord], int]],
        allowed: set[int],
    ) -> bool:
        if not loops:
            return False
        nodes: set[Coord] = set()
        for loop_nodes, _ in loops:
            nodes |= set(loop_nodes)
        for qid, pos in self.ctx.current_pos.items():
            if qid in allowed:
                continue
            if pos in nodes:
                return True
        return False

    @staticmethod
    def plans_compatible_distance(
        p1: _Plan,
        ab1: tuple[int, int],
        p2: _Plan,
        ab2: tuple[int, int],
    ) -> bool:
        a1, b1 = ab1
        a2, b2 = ab2
        length = max(p1.length, p2.length)

        def pos(plan: _Plan, qid: int, i: int) -> Coord:
            trace = plan.pos_trace[qid]
            if i < len(trace):
                return trace[i]
            return trace[-1]

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

    @staticmethod
    def plans_compatible_loops(p1: _Plan, p2: _Plan) -> bool:
        length = max(p1.length, p2.length)
        for i in range(length):
            d1 = {_LoopHelpers.canonical_loop_tuple(D) for D, _dir in p1.ticks[i].loops} if i < p1.length else set()

            d2 = {_LoopHelpers.canonical_loop_tuple(D) for D, _dir in p2.ticks[i].loops} if i < p2.length else set()

            if not d1.isdisjoint(d2):
                return False
        return True

    def group_parallel(self, plans: dict[tuple[int, int], _Plan]) -> list[list[tuple[int, int]]]:
        remaining_pids = sorted(plans.keys())
        groups: list[list[tuple[int, int]]] = []
        used: set[tuple[int, int]] = set()

        for pid in remaining_pids:
            if pid in used:
                continue
            grp = [pid]
            used.add(pid)
            for qid in remaining_pids:
                if qid in used:
                    continue
                ok = all(
                    self.plans_compatible_distance(plans[pid0], pid0, plans[qid], qid)
                    and self.plans_compatible_loops(plans[pid0], plans[qid])
                    for pid0 in grp
                )
                if ok:
                    grp.append(qid)
                    used.add(qid)
            groups.append(grp)

        return groups

    @staticmethod
    def build_pair_order(pairs: list[tuple[Qubit, Qubit]]) -> dict[tuple[int, int], int]:
        pair_order: dict[tuple[int, int], int] = {}
        for idx, (qa, qb) in enumerate(pairs):
            pair_order[qa.id, qb.id] = idx
        return pair_order

    @staticmethod
    def is_ready_pair(
        pid: tuple[int, int],
        remaining_pids: set[tuple[int, int]],
        pair_order: dict[tuple[int, int], int],
    ) -> bool:
        idx = pair_order[pid]
        a, b = pid
        for other in remaining_pids:
            if other == pid:
                continue
            j = pair_order[other]
            if j < idx:
                x, y = other
                if y in {a, b} or x in {a, b}:
                    return False
        return True

    def best_pre(self, meet: Coord, src: Coord) -> tuple[Coord, list[Coord]] | None:
        best: tuple[Coord, list[Coord]] | None = None
        for pre in self.ctx.sn_neighbors_of_meet(meet):
            p = self.ctx.shortest_path_sn(src, pre)
            if p is None:
                continue
            if best is None or len(p) < len(best[1]):
                best = (pre, p)
        return best

    def choose_meeting(
        self, la: Coord, lb: Coord
    ) -> tuple[Coord, tuple[Coord, list[Coord]], tuple[Coord, list[Coord]]] | None:
        cands = DefaultRoutingPlanner.best_meeting_candidates(
            self.ctx.graph, la, lb, reserved=set(), forbidden_nodes=set()
        )
        for m in cands:
            if not self.ctx.is_in(m):
                continue
            pa = self.best_pre(m, la)
            pb = self.best_pre(m, lb)
            if pa and pb:
                return (m, pa, pb)
        return None

    def commit_plan_sequential_with_retry(
        self,
        pid: tuple[int, int],
        plan: _Plan,
        *,
        allow_live_pre: bool = True,
    ) -> None:
        a_id, b_id = pid
        step = 0
        while step < plan.length:
            s = plan.ticks[step]

            pending_pre: dict[int, Coord] | None = None
            if allow_live_pre and plan.in_idx is not None and step == plan.in_idx:
                pending_pre = {
                    a_id: self.ctx.current_pos[a_id],
                    b_id: self.ctx.current_pos[b_id],
                }

            if allow_live_pre and plan.out_idx is not None and step == plan.out_idx:
                pre_map = self.live_pre_by_pair.get(
                    pid,
                    {a_id: self.ctx.current_pos[a_id], b_id: self.ctx.current_pos[b_id]},
                )
                s = _Step({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

            updates = self.expand_runtime_rotations(s.updates_pair_only, s.loops)
            moved = self.ctx.commit_tick(updates, sample=s.sample)

            if moved:
                if pending_pre is not None:
                    self.live_pre_by_pair[pid] = pending_pre
                step += 1


class _CirclePlannerEngine(_PlannerCommon):
    def circle_for_edge(
        self,
        u: Coord,
        v: Coord,
        target_lens: tuple[int, ...] = (6, 8),
    ) -> list[Coord] | None:
        if not (self.ctx.is_sn(u) and self.ctx.is_sn(v)):
            return None
        if not self.ctx.SN.has_edge(u, v):
            return None
        if _edgeset(u, v) in self.ctx.defective_edges:
            return None

        for target_len in target_lens:
            start = v
            max_nodes = target_len
            queue: deque[tuple[Coord, list[Coord]]] = deque()
            queue.append((start, [start]))

            while queue:
                node, path = queue.popleft()
                if len(path) >= max_nodes:
                    continue

                for w in self.ctx.SN.neighbors(node):
                    if _edgeset(node, w) in self.ctx.defective_edges:
                        continue

                    if w == u:
                        if _edgeset(node, u) in self.ctx.defective_edges:
                            continue
                        full_path = [*path, u]
                        if len(full_path) == max_nodes:
                            return [u, *path]
                        continue

                    if w in path:
                        continue

                    if len(path) + 1 <= max_nodes:
                        queue.append((w, [*path, w]))

        return None

    def plan_pair_solo(self, a_id: int, b_id: int) -> _Plan | None:
        la = self.ctx.current_pos[a_id]
        lb = self.ctx.current_pos[b_id]
        if not (self.ctx.is_sn(la) and self.ctx.is_sn(lb)):
            return None

        chosen = self.choose_meeting(la, lb)
        if not chosen:
            return None

        meet, (pre_a, path_a), (pre_b, path_b) = chosen
        ticks: list[_Step] = []
        trace: dict[int, list[Coord]] = {a_id: [la], b_id: [lb]}
        used_loops: set[tuple[Coord, ...]] = set()
        in_idx: int | None = None
        out_idx: int | None = None

        idx_a = 0
        idx_b = 0

        while la != pre_a or lb != pre_b:
            updates: dict[int, Coord] = {}
            loops_for_step: list[tuple[list[Coord], int]] = []

            if la != pre_a and idx_a + 1 < len(path_a):
                u_a, v_a = path_a[idx_a], path_a[idx_a + 1]
                if _is_diag(u_a, v_a):
                    loop_a = self.circle_for_edge(u_a, v_a)
                    if loop_a:
                        dir_a = _LoopHelpers.rot_dir_loop(loop_a, u_a, v_a)
                        upd_a = _LoopHelpers.compute_pair_rotation_updates_for_loop(loop_a, dir_a, a_id, b_id, la, lb)
                        upd_a[a_id] = v_a
                        updates.update(upd_a)
                        loops_for_step.append((loop_a, dir_a))
                        used_loops.add(_LoopHelpers.canonical_loop_tuple(loop_a))
                    else:
                        updates[a_id] = v_a
                else:
                    updates[a_id] = v_a

            if lb != pre_b and idx_b + 1 < len(path_b):
                u_b, v_b = path_b[idx_b], path_b[idx_b + 1]
                if _is_diag(u_b, v_b):
                    loop_b = self.circle_for_edge(u_b, v_b)
                    if loop_b:
                        dir_b = _LoopHelpers.rot_dir_loop(loop_b, u_b, v_b)
                        upd_b = _LoopHelpers.compute_pair_rotation_updates_for_loop(loop_b, dir_b, a_id, b_id, la, lb)
                        upd_b[b_id] = v_b
                        if not (loops_for_step and set(loops_for_step[0][0]).intersection(loop_b)):
                            updates.update(upd_b)
                            loops_for_step.append((loop_b, dir_b))
                            used_loops.add(_LoopHelpers.canonical_loop_tuple(loop_b))
                    elif b_id not in updates:
                        updates[b_id] = v_b
                elif b_id not in updates:
                    updates[b_id] = v_b

            if not updates:
                return None

            la = updates.get(a_id, la)
            lb = updates.get(b_id, lb)
            if a_id in updates:
                idx_a = min(idx_a + 1, len(path_a) - 1)
            if b_id in updates:
                idx_b = min(idx_b + 1, len(path_b) - 1)

            ticks.append(_Step(updates, loops_for_step, sample=True))
            trace[a_id].append(la)
            trace[b_id].append(lb)

        updates_in: dict[int, Coord] = {}
        if la != meet:
            updates_in[a_id] = meet
        if lb != meet:
            updates_in[b_id] = meet

        if updates_in:
            la = updates_in.get(a_id, la)
            lb = updates_in.get(b_id, lb)
            in_idx = len(ticks)
            ticks.append(_Step(updates_in, [], sample=True))
            trace[a_id].append(la)
            trace[b_id].append(lb)

        out_idx = len(ticks)
        ticks.append(_Step({}, [], sample=False))
        trace[a_id].append(pre_a)
        trace[b_id].append(pre_b)

        return _Plan(ticks, trace, used_loops, in_idx, out_idx)

    def run(self, pairs: list[tuple[Qubit, Qubit]]) -> RoutingResult:
        pair_order = self.build_pair_order(pairs)
        remaining: set[tuple[int, int]] = {(qa.id, qb.id) for qa, qb in pairs}

        while remaining:
            ready_pids = [pid for pid in remaining if self.is_ready_pair(pid, remaining, pair_order)]
            if not ready_pids:
                ready_pids = list(remaining)

            plans: dict[tuple[int, int], _Plan] = {}
            sequential_fallback: list[tuple[int, int]] = []

            for pid in sorted(ready_pids, key=lambda p: pair_order[p]):
                a, b = pid
                plan = self.plan_pair_solo(a, b)
                if plan is None:
                    sequential_fallback.append(pid)
                else:
                    plans[pid] = plan

            if not plans and not sequential_fallback:
                self.ctx.commit_tick({}, sample=True)
                break

            groups = self.group_parallel(plans) if plans else []
            something_finished = False

            for grp in groups:
                group_qids: set[int] = {x for ab in grp for x in ab}
                length = max(plans[pid].length for pid in grp) if grp else 0
                parallel_failed = False
                step = 0

                while step < length:
                    updates_pair_only: dict[int, Coord] = {}
                    sample_flags: list[bool] = []
                    step_loops: list[tuple[list[Coord], int]] = []
                    pending_live_pre: dict[tuple[int, int], dict[int, Coord]] = {}
                    conflict = False

                    for pid in grp:
                        plan = plans[pid]
                        s = plan.ticks[step] if step < plan.length else _Step({}, [], sample=True)

                        if plan.in_idx is not None and step == plan.in_idx:
                            a_id, b_id = pid
                            pending_live_pre[pid] = {
                                a_id: self.ctx.current_pos[a_id],
                                b_id: self.ctx.current_pos[b_id],
                            }

                        if plan.out_idx is not None and step == plan.out_idx:
                            a_id, b_id = pid
                            pre_map = self.live_pre_by_pair.get(
                                pid,
                                {
                                    a_id: self.ctx.current_pos[a_id],
                                    b_id: self.ctx.current_pos[b_id],
                                },
                            )
                            s = _Step({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

                        if set(updates_pair_only.keys()) & set(s.updates_pair_only.keys()):
                            conflict = True
                            break

                        updates_pair_only.update(s.updates_pair_only)
                        sample_flags.append(s.sample)
                        step_loops.extend(s.loops)

                    if conflict or self.foreign_qubits_on_any_loop(step_loops, allowed=group_qids):
                        parallel_failed = True
                        break

                    updates = self.expand_runtime_rotations(updates_pair_only, step_loops)
                    do_sample = False not in sample_flags
                    moved = self.ctx.commit_tick(updates, sample=do_sample)

                    if moved:
                        for pid, pre in pending_live_pre.items():
                            self.live_pre_by_pair[pid] = pre
                        step += 1

                if parallel_failed:
                    for pid in grp:
                        self.commit_plan_sequential_with_retry(pid, plans[pid])

                remaining.difference_update(grp)

                something_finished = True
                break

            if not something_finished:
                if sequential_fallback:
                    pid = sequential_fallback[0]
                    plan = self.plan_pair_solo(*pid)
                    if plan is None:
                        self.ctx.commit_tick({}, sample=True)
                    else:
                        self.commit_plan_sequential_with_retry(pid, plan)
                    remaining.discard(pid)
                else:
                    self.ctx.commit_tick({}, sample=True)

        return self.ctx.timelines, self.ctx.edge_timebands


class _HybridPlannerEngine(_PlannerCommon):
    def diamond_for_edge(self, u: Coord, v: Coord) -> list[Coord] | None:
        return _DiamondHelpers.diamond_for_edge(self.ctx.graph, self.ctx.is_sn, u, v)

    def circle_for_edge(
        self,
        u: Coord,
        v: Coord,
        target_lens: tuple[int, ...] = (6, 8),
    ) -> list[Coord] | None:
        if not (self.ctx.is_sn(u) and self.ctx.is_sn(v)):
            return None
        if not self.ctx.SN.has_edge(u, v):
            return None
        if _edgeset(u, v) in self.ctx.defective_edges:
            return None

        for target_len in target_lens:
            max_nodes = target_len
            queue: deque[tuple[Coord, list[Coord]]] = deque()
            queue.append((v, [v]))

            while queue:
                node, path = queue.popleft()
                if len(path) >= max_nodes:
                    continue

                for w in self.ctx.SN.neighbors(node):
                    if _edgeset(node, w) in self.ctx.defective_edges:
                        continue

                    if w == u:
                        if _edgeset(node, u) in self.ctx.defective_edges:
                            continue
                        full_path = [*path, u]
                        if len(full_path) == max_nodes:
                            return [u, *path]
                        continue

                    if w in path:
                        continue

                    if len(path) + 1 <= max_nodes:
                        queue.append((w, [*path, w]))

        return None

    def plan_pair_rotation(self, a_id: int, b_id: int) -> _Plan | None:
        la = self.ctx.current_pos[a_id]
        lb = self.ctx.current_pos[b_id]
        if not (self.ctx.is_sn(la) and self.ctx.is_sn(lb)):
            return None

        chosen = self.choose_meeting(la, lb)
        if not chosen:
            return None

        meet, (pre_a, path_a), (pre_b, path_b) = chosen
        ticks: list[_Step] = []
        trace: dict[int, list[Coord]] = {a_id: [la], b_id: [lb]}
        used: set[tuple[Coord, ...]] = set()
        in_idx: int | None = None
        out_idx: int | None = None

        idx_a = 0
        idx_b = 0

        while la != pre_a or lb != pre_b:
            updates: dict[int, Coord] = {}
            loops_for_step: list[tuple[list[Coord], int]] = []

            if la != pre_a and idx_a + 1 < len(path_a):
                u_a, v_a = path_a[idx_a], path_a[idx_a + 1]
                if _is_diag(u_a, v_a):
                    d_a = self.diamond_for_edge(u_a, v_a)
                    if d_a:
                        dir_a = _DiamondHelpers.rot_dir_diamond(d_a, u_a, v_a)
                        upd_a = _DiamondHelpers.compute_pair_rotation_updates_for_diamond(
                            d_a, dir_a, a_id, b_id, la, lb
                        )
                        upd_a[a_id] = v_a
                        updates.update(upd_a)
                        loops_for_step.append((d_a, dir_a))
                        used.add(_LoopHelpers.canonical_loop_tuple(d_a))
                    else:
                        updates[a_id] = v_a
                else:
                    updates[a_id] = v_a

            if lb != pre_b and idx_b + 1 < len(path_b):
                u_b, v_b = path_b[idx_b], path_b[idx_b + 1]
                if _is_diag(u_b, v_b):
                    d_b = self.diamond_for_edge(u_b, v_b)
                    if d_b:
                        dir_b = _DiamondHelpers.rot_dir_diamond(d_b, u_b, v_b)
                        upd_b = _DiamondHelpers.compute_pair_rotation_updates_for_diamond(
                            d_b, dir_b, a_id, b_id, la, lb
                        )
                        upd_b[b_id] = v_b
                        if not (loops_for_step and set(loops_for_step[0][0]).intersection(d_b)):
                            updates.update(upd_b)
                            loops_for_step.append((d_b, dir_b))
                            used.add(_LoopHelpers.canonical_loop_tuple(d_b))
                    elif b_id not in updates:
                        updates[b_id] = v_b
                elif b_id not in updates:
                    updates[b_id] = v_b

            if not updates:
                return None

            la = updates.get(a_id, la)
            lb = updates.get(b_id, lb)
            if a_id in updates:
                idx_a = min(idx_a + 1, len(path_a) - 1)
            if b_id in updates:
                idx_b = min(idx_b + 1, len(path_b) - 1)

            ticks.append(_Step(updates, loops_for_step, sample=True))
            trace[a_id].append(la)
            trace[b_id].append(lb)

        updates_in: dict[int, Coord] = {}
        if la != meet:
            updates_in[a_id] = meet
        if lb != meet:
            updates_in[b_id] = meet

        if updates_in:
            la = updates_in.get(a_id, la)
            lb = updates_in.get(b_id, lb)
            in_idx = len(ticks)
            ticks.append(_Step(updates_in, [], sample=True))
            trace[a_id].append(la)
            trace[b_id].append(lb)

        out_idx = len(ticks)
        ticks.append(_Step({}, [], sample=False))
        trace[a_id].append(pre_a)
        trace[b_id].append(pre_b)

        return _Plan(ticks, trace, used, in_idx, out_idx)

    def plan_pair_circle(self, id_a: int, id_b: int) -> _Plan | None:
        la = self.ctx.current_pos[id_a]
        lb = self.ctx.current_pos[id_b]
        if not (self.ctx.is_sn(la) and self.ctx.is_sn(lb)):
            return None

        chosen = self.choose_meeting(la, lb)
        if not chosen:
            return None

        meet, (pre_a, path_a), (pre_b, path_b) = chosen
        ticks: list[_Step] = []
        trace: dict[int, list[Coord]] = {id_a: [la], id_b: [lb]}
        used: set[tuple[Coord, ...]] = set()
        in_idx: int | None = None
        out_idx: int | None = None

        idx_a = 0
        idx_b = 0

        while la != pre_a or lb != pre_b:
            updates: dict[int, Coord] = {}
            loops_for_step: list[tuple[list[Coord], int]] = []

            if la != pre_a and idx_a + 1 < len(path_a):
                u_a, v_a = path_a[idx_a], path_a[idx_a + 1]
                if _is_diag(u_a, v_a):
                    loop_a = self.circle_for_edge(u_a, v_a)
                    if loop_a:
                        dir_a = _LoopHelpers.rot_dir_loop(loop_a, u_a, v_a)
                        upd_a = _LoopHelpers.compute_pair_rotation_updates_for_loop(loop_a, dir_a, id_a, id_b, la, lb)
                        upd_a[id_a] = v_a
                        updates.update(upd_a)
                        loops_for_step.append((loop_a, dir_a))
                        used.add(_LoopHelpers.canonical_loop_tuple(loop_a))
                    else:
                        updates[id_a] = v_a
                else:
                    updates[id_a] = v_a

            if lb != pre_b and idx_b + 1 < len(path_b):
                u_b, v_b = path_b[idx_b], path_b[idx_b + 1]
                if _is_diag(u_b, v_b):
                    loop_b = self.circle_for_edge(u_b, v_b)
                    if loop_b:
                        dir_b = _LoopHelpers.rot_dir_loop(loop_b, u_b, v_b)
                        upd_b = _LoopHelpers.compute_pair_rotation_updates_for_loop(loop_b, dir_b, id_a, id_b, la, lb)
                        upd_b[id_b] = v_b
                        if not (loops_for_step and set(loops_for_step[0][0]).intersection(loop_b)):
                            updates.update(upd_b)
                            loops_for_step.append((loop_b, dir_b))
                            used.add(_LoopHelpers.canonical_loop_tuple(loop_b))
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

            ticks.append(_Step(updates, loops_for_step, sample=True))
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
            ticks.append(_Step(updates_in, [], sample=True))
            trace[id_a].append(la)
            trace[id_b].append(lb)

        out_idx = len(ticks)
        ticks.append(_Step({}, [], sample=False))
        trace[id_a].append(pre_a)
        trace[id_b].append(pre_b)

        return _Plan(ticks, trace, used, in_idx, out_idx)

    def run(self, pairs: list[tuple[Qubit, Qubit]]) -> RoutingResult:
        pair_order = self.build_pair_order(pairs)
        remaining: set[tuple[int, int]] = {(qa.id, qb.id) for qa, qb in pairs}

        while remaining:
            ready_pids = [pid for pid in remaining if self.is_ready_pair(pid, remaining, pair_order)]
            if not ready_pids:
                ready_pids = list(remaining)

            plans: dict[tuple[int, int], _Plan] = {}
            sequential_fallback: list[tuple[int, int]] = []

            for pid in sorted(ready_pids, key=lambda p: pair_order[p]):
                a, b = pid
                plan = self.plan_pair_rotation(a, b)
                if plan is None:
                    sequential_fallback.append(pid)
                else:
                    plans[pid] = plan

            if not plans and not sequential_fallback:
                self.ctx.commit_tick({}, sample=True)
                break

            groups = self.group_parallel(plans) if plans else []
            something_finished = False

            for grp in groups:
                group_qids: set[int] = {x for ab in grp for x in ab}
                length = max(plans[pid].length for pid in grp) if grp else 0
                parallel_failed = False
                step = 0

                while step < length:
                    updates_pair_only: dict[int, Coord] = {}
                    sample_flags: list[bool] = []
                    step_loops: list[tuple[list[Coord], int]] = []
                    pending_live_pre: dict[tuple[int, int], dict[int, Coord]] = {}
                    conflict = False

                    for pid in grp:
                        plan = plans[pid]
                        s = plan.ticks[step] if step < plan.length else _Step({}, [], sample=True)

                        if plan.in_idx is not None and step == plan.in_idx:
                            a_id, b_id = pid
                            pending_live_pre[pid] = {
                                a_id: self.ctx.current_pos[a_id],
                                b_id: self.ctx.current_pos[b_id],
                            }

                        if plan.out_idx is not None and step == plan.out_idx:
                            a_id, b_id = pid
                            pre_map = self.live_pre_by_pair.get(
                                pid,
                                {
                                    a_id: self.ctx.current_pos[a_id],
                                    b_id: self.ctx.current_pos[b_id],
                                },
                            )
                            s = _Step({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

                        if set(updates_pair_only.keys()) & set(s.updates_pair_only.keys()):
                            conflict = True
                            break

                        updates_pair_only.update(s.updates_pair_only)
                        sample_flags.append(s.sample)
                        step_loops.extend(s.loops)

                    if conflict or self.foreign_qubits_on_any_loop(step_loops, allowed=group_qids):
                        parallel_failed = True
                        break

                    updates = self.expand_runtime_rotations(updates_pair_only, step_loops)
                    do_sample = False not in sample_flags
                    moved = self.ctx.commit_tick(updates, sample=do_sample)

                    if moved:
                        for pid, pre in pending_live_pre.items():
                            self.live_pre_by_pair[pid] = pre
                        step += 1

                if parallel_failed:
                    for pid in grp:
                        a_id, b_id = pid
                        plan = plans[pid]
                        use_circle = False
                        tried_circle = False

                        step_seq = 0
                        while step_seq < plan.length:
                            s = plan.ticks[step_seq]

                            pending_pre: dict[int, Coord] | None = None
                            if plan.in_idx is not None and step_seq == plan.in_idx:
                                pending_pre = {
                                    a_id: self.ctx.current_pos[a_id],
                                    b_id: self.ctx.current_pos[b_id],
                                }

                            if plan.out_idx is not None and step_seq == plan.out_idx:
                                pre_map = self.live_pre_by_pair.get(
                                    pid,
                                    {
                                        a_id: self.ctx.current_pos[a_id],
                                        b_id: self.ctx.current_pos[b_id],
                                    },
                                )
                                s = _Step({a_id: pre_map[a_id], b_id: pre_map[b_id]}, [], sample=False)

                            updates = self.expand_runtime_rotations(s.updates_pair_only, s.loops)
                            moved = self.ctx.commit_tick(updates, sample=s.sample)

                            if moved:
                                if pending_pre is not None:
                                    self.live_pre_by_pair[pid] = pending_pre
                                step_seq += 1
                                continue

                            if (not use_circle) and (not tried_circle):
                                tried_circle = True
                                circle_plan = self.plan_pair_circle(a_id, b_id)
                                if circle_plan is not None:
                                    use_circle = True
                                    plan = circle_plan
                                    step_seq = 0

                remaining.difference_update(grp)

                something_finished = True
                break

            if not something_finished:
                if sequential_fallback:
                    pid = sequential_fallback[0]
                    a, b = pid

                    plan = self.plan_pair_rotation(a, b)
                    use_circle = False
                    tried_circle = False

                    if plan is None:
                        plan = self.plan_pair_circle(a, b)
                        if plan is not None:
                            use_circle = True

                    if plan is None:
                        self.ctx.commit_tick({}, sample=True)
                    else:
                        step_seq = 0
                        while step_seq < plan.length:
                            s = plan.ticks[step_seq]

                            pending_pre: dict[int, Coord] | None = None
                            if plan.in_idx is not None and step_seq == plan.in_idx:
                                pending_pre = {
                                    a: self.ctx.current_pos[a],
                                    b: self.ctx.current_pos[b],
                                }

                            if plan.out_idx is not None and step_seq == plan.out_idx:
                                pre_map = self.live_pre_by_pair.get(
                                    pid,
                                    {a: self.ctx.current_pos[a], b: self.ctx.current_pos[b]},
                                )
                                s = _Step({a: pre_map[a], b: pre_map[b]}, [], sample=False)

                            updates = self.expand_runtime_rotations(s.updates_pair_only, s.loops)
                            moved = self.ctx.commit_tick(updates, sample=s.sample)

                            if moved:
                                if pending_pre is not None:
                                    self.live_pre_by_pair[pid] = pending_pre
                                step_seq += 1
                                continue

                            if (not use_circle) and (not tried_circle):
                                tried_circle = True
                                circle_plan = self.plan_pair_circle(a, b)
                                if circle_plan is not None:
                                    use_circle = True
                                    plan = circle_plan
                                    step_seq = 0

                    remaining.discard(pid)
                else:
                    self.ctx.commit_tick({}, sample=True)

        return self.ctx.timelines, self.ctx.edge_timebands


class CircleRotationRoutingPlanner:
    @staticmethod
    def route(
        graph: nx.Graph,
        qubits: list[Qubit],
        pairs: list[tuple[Qubit, Qubit]],
        p_success: float,
        p_repair: float,
    ) -> RoutingResult:
        ctx = _RoutingContext(graph, qubits, p_success, p_repair)
        engine = _CirclePlannerEngine(ctx)
        return engine.run(pairs)


class HybridRotationRoutingPlanner(RoutingStrategy):
    @override
    def route(
        self,
        graph: nx.Graph,
        qubits: list[Qubit],
        pairs: list[tuple[Qubit, Qubit]],
        p_success: float,
        p_repair: float,
    ) -> RoutingResult:
        ctx = _RoutingContext(
            graph,
            qubits,
            p_success,
            p_repair,
            max_wait_time=MAX_WAIT_TIME,
            stuck_error_prefix="Routing stuck (Hybrid)",
        )
        engine = _HybridPlannerEngine(ctx)
        return engine.run(pairs)
