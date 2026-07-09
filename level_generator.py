"""
Compact multi-phase chamber puzzles for curation.

Primary joke is no longer "one switch → open exit". Templates force
at least two decisions (two chains / two remotes in series).

Layouts stay small (one screen). Outer loop rejects trivial solutions.

Edge keys:
  ("v", x, y) — vertical edge at column-line x, row y
  ("h", x, y) — horizontal edge at row-line y, col x
"""

import random
from collections import deque


def generate_level(w=None, h=None, level_num=0, difficulty=None):
    if difficulty is None:
        difficulty = max(0, int(level_num))

    if w is None:
        w = min(6 + difficulty // 3, 8)
    if h is None:
        h = min(5 + difficulty // 3, 7)

    # Weighted template mix — prefer multi-phase structures
    roll = random.random()
    builders = []
    if roll < 0.55:
        builders = [_generate_two_phase, _generate_two_phase, _generate_cross_link]
    elif roll < 0.85:
        builders = [_generate_cross_link, _generate_two_phase]
    else:
        builders = [_generate_simple_switch, _generate_two_phase]

    for builder in builders:
        for _ in range(6):
            result = builder(w, h, difficulty)
            if result is not None:
                return result

    # Last resorts
    for builder in (_generate_two_phase, _generate_cross_link, _generate_simple_switch):
        result = builder(max(w, 6), max(h, 5), difficulty)
        if result is not None:
            return result
    return _minimal_fallback(w, h)


# ---------------------------------------------------------------------------
# Template A: two serial remotes (true multi-phase)
# ---------------------------------------------------------------------------

def _generate_two_phase(w, h, difficulty):
    """
    Four chambers:

        +--------+--------+
        | SWITCH |  GOAL  |
        |  [S1]  |   X    |
        +---g----+--R2----+
        | ENTRY  |  MID   |
        |   P    |  [S2]  |
        +--------+--R1----  (R1 on vertical between entry|mid)

    R1 (remote) blocks entry→mid, opened by S1 in switch.
    R2 (remote) blocks mid→goal, opened by S2 in mid.
    After S1 only, exit still unreachable → multi-phase.
    """
    if w < 6 or h < 5:
        w, h = max(w, 6), max(h, 5)

    walls = _outer_walls_only(w, h)
    vx = max(2, min(w // 2, w - 3))
    hy = max(2, min(h // 2, h - 2))

    # Vertical macro cut
    for y in range(h):
        walls.add(("v", vx, y))
    # Horizontal cuts on both sides
    for x in range(w):
        walls.add(("h", x, hy))

    # Portals
    # Switch entry: gap on left horizontal
    g_x = max(0, min(vx - 1, vx // 2))
    switch_entry = ("h", g_x, hy)
    walls.discard(switch_entry)

    # R1: entry (left-bottom) → mid (right-bottom)
    r1_ys = [y for y in range(hy, h) if 0 < y < h - 1]
    if not r1_ys:
        r1_ys = list(range(hy, h))
    r1_y = random.choice(r1_ys)
    r1 = ("v", vx, r1_y)
    walls.discard(r1)
    _force_flanks(walls, r1, w, h)

    # R2: mid (right-bottom) → goal (right-top)
    r2_xs = [x for x in range(vx, w) if 0 < x < w - 1]
    if not r2_xs:
        r2_xs = list(range(vx, w))
    r2_x = random.choice(r2_xs)
    r2 = ("h", r2_x, hy)
    walls.discard(r2)
    _force_flanks(walls, r2, w, h)

    # Seal left-top from right-top (already have vertical wall)
    # Optional: no direct switch→goal portal (forces path through mid)

    switch_cells = [(x, y) for y in range(hy) for x in range(vx)]
    entry_cells = [(x, y) for y in range(hy, h) for x in range(vx)]
    mid_cells = [(x, y) for y in range(hy, h) for x in range(vx, w)]
    goal_cells = [(x, y) for y in range(hy) for x in range(vx, w)]

    if not all([switch_cells, entry_cells, mid_cells, goal_cells]):
        return None

    # Light detail only
    for cells in (switch_cells, entry_cells, mid_cells, goal_cells):
        _light_chamber_detail(walls, cells, w, h, {switch_entry, r1, r2})

    # Re-seal macros except portals
    for y in range(h):
        e = ("v", vx, y)
        if e != r1:
            walls.add(e)
        else:
            walls.discard(e)
    for x in range(w):
        e = ("h", x, hy)
        if e in (switch_entry, r2):
            walls.discard(e)
        else:
            walls.add(e)

    s1 = _place_control_in_region(walls, switch_cells, w, h, {switch_entry, r1, r2})
    s2 = _place_control_in_region(walls, mid_cells, w, h, {switch_entry, r1, r2, s1} if s1 else {switch_entry, r1, r2})
    if s1 is None or s2 is None or s1 == s2:
        return None

    player = _pick_cell(entry_cells, prefer=(g_x, min(h - 1, hy)))
    exit_pos = _pick_cell(goal_cells, prefer=(w - 1, 0))

    doors = {
        s1: {
            "state": 0,
            "linked": [list(r1)],
            "kind": "onesided" if random.random() < 0.55 else "local",
            "handle": _handle_toward(s1, (vx // 2, hy // 2)),
        },
        r1: {
            "state": 1,
            "linked": [list(s1)],
            "kind": "remote",
            "handle": "a",
        },
        s2: {
            "state": 0,
            "linked": [list(r2)],
            "kind": "onesided" if random.random() < 0.45 else "local",
            "handle": _handle_toward(s2, (vx + 1, hy + 1)),
        },
        r2: {
            "state": 1,
            "linked": [list(s2)],
            "kind": "remote",
            "handle": "a",
        },
    }
    if doors[s1]["kind"] != "onesided":
        doors[s1]["handle"] = "a"
    if doors[s2]["kind"] != "onesided":
        doors[s2]["handle"] = "a"

    # Structural checks with real door open/closed (gaps are doors, not free air)
    open_all = {e: 0 for e in doors}
    only_r1 = {e: doors[e]["state"] for e in doors}
    only_r1[r1] = 0
    only_r1[s1] = 1  # after flipping chain1: r1 open, s1 closed
    # Actually after flip of s1-r1: both toggle — r1:1→0, s1:0→1
    after_s1 = {e: doors[e]["state"] for e in doors}
    after_s1[r1] = 0
    after_s1[s1] = 1

    if exit_pos not in _reachable(player, w, h, walls, doors, open_all):
        return None
    # After only first chain flip, exit still blocked (need s2)
    if exit_pos in _reachable(player, w, h, walls, doors, after_s1):
        return None
    # Mid should be reachable after first chain
    mid_anchor = mid_cells[0]
    if mid_anchor not in _reachable(player, w, h, walls, doors, after_s1):
        return None

    return _finalize(w, h, walls, player, exit_pos, doors, switch_entry)


# ---------------------------------------------------------------------------
# Template B: cross-link (opening A messes with B)
# ---------------------------------------------------------------------------

def _generate_cross_link(w, h, difficulty):
    """
    Three doors on one chain with mixed polarity, plus a second independent
    remote on the exit. S in switch flips chain that opens mid-gate but
    closes something — actually simpler:

    Chain A: S1 <-> R_exit (opposite)  — classic
    Chain B: S2 <-> R_block on path to S1  — must open R_block first via S2
             then go to S1, then exit.

    S2 in entry (local), R_block between entry and switch path,
    S1 in switch, R_exit to goal.
    """
    if w < 6 or h < 5:
        w, h = max(w, 6), max(h, 5)

    walls = _outer_walls_only(w, h)
    vx = max(2, min(w // 2, w - 3))
    hy = max(2, min(h // 2, h - 2))

    for y in range(h):
        walls.add(("v", vx, y))
    for x in range(vx):
        walls.add(("h", x, hy))

    # Switch entry is a REMOTE (blocked until S2)
    g_x = max(0, min(vx - 1, vx // 2))
    r_block = ("h", g_x, hy)
    walls.discard(r_block)
    _force_flanks(walls, r_block, w, h)

    # Exit remote on vertical cut
    r_ys = [y for y in range(0, h) if 0 < y < h - 1]
    r_y = random.choice(r_ys) if r_ys else h // 2
    # Prefer exit in lower or upper — put exit chamber on right
    r_exit = ("v", vx, r_y)
    walls.discard(r_exit)
    _force_flanks(walls, r_exit, w, h)

    for y in range(h):
        e = ("v", vx, y)
        if e != r_exit:
            walls.add(e)
        else:
            walls.discard(e)
    for x in range(vx):
        e = ("h", x, hy)
        if e != r_block:
            walls.add(e)
        else:
            walls.discard(e)

    switch_cells = [(x, y) for y in range(hy) for x in range(vx)]
    entry_cells = [(x, y) for y in range(hy, h) for x in range(vx)]
    # Right side open as exit wing
    exit_cells = [(x, y) for y in range(h) for x in range(vx, w)]

    s1 = _place_control_in_region(walls, switch_cells, w, h, {r_block, r_exit})
    s2 = _place_control_in_region(walls, entry_cells, w, h, {r_block, r_exit, s1} if s1 else {r_block, r_exit})
    if s1 is None or s2 is None or s1 == s2:
        return None

    player = _pick_cell(entry_cells)
    exit_pos = _pick_cell(exit_cells)

    doors = {
        s2: {
            "state": 0,
            "linked": [list(r_block)],
            "kind": "local",
            "handle": "a",
        },
        r_block: {
            "state": 1,
            "linked": [list(s2)],
            "kind": "remote",
            "handle": "a",
        },
        s1: {
            "state": 0,
            "linked": [list(r_exit)],
            "kind": "onesided" if random.random() < 0.6 else "local",
            "handle": _handle_toward(s1, (vx // 2, hy // 2)),
        },
        r_exit: {
            "state": 1,
            "linked": [list(s1)],
            "kind": "remote",
            "handle": "a",
        },
    }
    if doors[s1]["kind"] != "onesided":
        doors[s1]["handle"] = "a"

    open_all = {e: 0 for e in doors}
    after_s2 = {e: doors[e]["state"] for e in doors}
    after_s2[r_block] = 0
    after_s2[s2] = 1
    # start: blocked
    start_map = {e: doors[e]["state"] for e in doors}
    if exit_pos in _reachable(player, w, h, walls, doors, start_map):
        return None
    if exit_pos not in _reachable(player, w, h, walls, doors, open_all):
        return None
    # After only opening block, exit still closed (need s1)
    if exit_pos in _reachable(player, w, h, walls, doors, after_s2):
        return None
    # Switch reachable after s2
    sw = switch_cells[0]
    if sw not in _reachable(player, w, h, walls, doors, after_s2):
        return None

    return _finalize(w, h, walls, player, exit_pos, doors, None)


# ---------------------------------------------------------------------------
# Template C: simple switch (mostly filtered out as trivial)
# ---------------------------------------------------------------------------

def _generate_simple_switch(w, h, difficulty):
    if w < 5 or h < 4:
        w, h = max(w, 5), max(h, 4)
    walls = _outer_walls_only(w, h)
    vx = max(2, min(w // 2, w - 2))
    hy = max(2, min(h // 2, h - 2))
    for y in range(h):
        walls.add(("v", vx, y))
    for x in range(vx):
        walls.add(("h", x, hy))
    g_x = max(0, min(vx - 1, vx // 2))
    switch_entry = ("h", g_x, hy)
    walls.discard(switch_entry)
    ey = random.choice([y for y in range(hy, h) if 0 < y < h - 1] or [min(h - 2, hy)])
    r = ("v", vx, ey)
    walls.discard(r)
    _force_flanks(walls, r, w, h)
    for y in range(h):
        e = ("v", vx, y)
        if e != r:
            walls.add(e)
        else:
            walls.discard(e)
    for x in range(vx):
        e = ("h", x, hy)
        if e != switch_entry:
            walls.add(e)
        else:
            walls.discard(e)

    switch_cells = [(x, y) for y in range(hy) for x in range(vx)]
    entry_cells = [(x, y) for y in range(hy, h) for x in range(vx)]
    exit_cells = [(x, y) for y in range(h) for x in range(vx, w)]
    s = _place_control_in_region(walls, switch_cells, w, h, {switch_entry, r})
    if s is None:
        s = _place_midrun_control(walls, vx, hy, w, h)
    if s is None:
        return None
    player = _pick_cell(entry_cells)
    exit_pos = _pick_cell(exit_cells)
    doors = {
        s: {"state": 0, "linked": [list(r)], "kind": "onesided", "handle": _handle_toward(s, (vx // 2, hy // 2))},
        r: {"state": 1, "linked": [list(s)], "kind": "remote", "handle": "a"},
    }
    return _finalize(w, h, walls, player, exit_pos, doors, switch_entry)


def _minimal_fallback(w, h):
    w, h = max(w, 6), max(h, 5)
    result = _generate_two_phase(w, h, 2)
    if result:
        return result
    return _generate_simple_switch(w, h, 0)


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------

def _finalize(w, h, walls, player, exit_pos, doors, open_portal):
    bad = _embed_all_doors_in_walls(doors, walls, w, h)
    if bad:
        return None
    for e in doors:
        walls.discard(e)
    if open_portal is not None:
        walls.discard(open_portal)
    if not _all_doors_are_wall_gaps(doors, walls, w, h):
        return None

    state_map = {e: d["state"] for e, d in doors.items()}
    if len(_neighbors(*player, w, h, walls, doors, state_map)) == 0:
        return None
    if exit_pos in _reachable(player, w, h, walls, doors, state_map):
        return None
    open_map = {e: 0 for e in doors}
    if exit_pos not in _reachable(player, w, h, walls, doors, open_map):
        return None
    return w, h, walls, player, exit_pos, doors


def _force_flanks(walls, edge, w, h):
    for n in _collinear_neighbors(edge, w, h):
        walls.add(n)
    walls.discard(edge)


def _place_control_in_region(walls, cells, w, h, protected):
    """Prefer existing fully-flanked wall; else build mid-run in region."""
    cell_set = set(cells)
    protected = set(p for p in protected if p)
    cands = []
    for x, y in cell_set:
        for nx, ny, edge in (
            (x + 1, y, ("v", x + 1, y)),
            (x, y + 1, ("h", x, y + 1)),
        ):
            if (nx, ny) not in cell_set or edge in protected:
                continue
            if edge in walls and _door_is_fully_flanked(edge, walls, w, h):
                if len(_collinear_neighbors(edge, w, h)) >= 2:
                    cands.append(edge)
    if cands:
        e = random.choice(cands)
        walls.discard(e)
        return e
    return _build_midrun_in_cells(walls, cells, w, h, protected)


def _build_midrun_in_cells(walls, cells, w, h, protected):
    cell_set = set(cells)
    # Try vertical mid-run
    by_col = {}
    for x, y in cell_set:
        by_col.setdefault(x, []).append(y)
    cols = [x for x, ys in by_col.items() if len(ys) >= 3]
    random.shuffle(cols)
    for x in cols:
        ys = sorted(by_col[x])
        # door at middle row that has y-1 and y+1 in set as cells for vertical edge
        for y in ys:
            if y - 1 in ys or y + 1 in ys:
                # vertical edge ("v", x, y) needs cells (x-1,y) and (x,y) — use interior x
                pass
    # Simpler: pick three collinear internal edges
    for x, y in cell_set:
        if (x + 1, y) in cell_set and (x + 2, y) in cell_set:
            # edges between them vertical at x+1 and x+2
            e0, e1, e2 = ("v", x + 1, y), ("v", x + 2, y), None
            # need three segments: use horizontal run instead
        if (x, y + 1) in cell_set and (x, y + 2) in cell_set:
            # vertical wall line at x+? edges ("h" between rows)
            pass

    # Vertical line at ax between columns ax-1 and ax, three rows
    for ax in range(1, w):
        rows = [y for y in range(h) if (ax - 1, y) in cell_set and (ax, y) in cell_set]
        rows = sorted(rows)
        for i in range(len(rows) - 2):
            y0, y1, y2 = rows[i], rows[i + 1], rows[i + 2]
            if y1 != y0 + 1 or y2 != y1 + 1:
                continue
            # consecutive rows — walls on ("v", ax, y0..y2)
            ctrl = ("v", ax, y1)
            if ctrl in protected:
                continue
            walls.add(("v", ax, y0))
            walls.discard(ctrl)
            walls.add(("v", ax, y2))
            return ctrl

    for ay in range(1, h):
        cols = [x for x in range(w) if (x, ay - 1) in cell_set and (x, ay) in cell_set]
        cols = sorted(cols)
        for i in range(len(cols) - 2):
            x0, x1, x2 = cols[i], cols[i + 1], cols[i + 2]
            if x1 != x0 + 1 or x2 != x1 + 1:
                continue
            ctrl = ("h", x1, ay)
            if ctrl in protected:
                continue
            walls.add(("h", x0, ay))
            walls.discard(ctrl)
            walls.add(("h", x2, ay))
            return ctrl
    return None


def _place_midrun_control(walls, vx, hy, w, h):
    if hy >= 3 and vx >= 2:
        ax = random.randint(1, vx - 1)
        door_y = random.randint(1, hy - 2)
        ctrl = ("v", ax, door_y)
        walls.add(("v", ax, door_y - 1))
        walls.discard(ctrl)
        walls.add(("v", ax, door_y + 1))
        return ctrl
    if hy >= 2 and vx >= 3:
        line_y = random.randint(1, hy - 1)
        x_mid = random.randint(1, vx - 2)
        ctrl = ("h", x_mid, line_y)
        walls.add(("h", x_mid - 1, line_y))
        walls.discard(ctrl)
        walls.add(("h", x_mid + 1, line_y))
        return ctrl
    return None


def _light_chamber_detail(walls, cells, w, h, protected):
    if len(cells) < 6 or random.random() < 0.5:
        return
    cell_set = set(cells)
    cands = []
    for x, y in cell_set:
        for nx, ny, edge in (
            (x + 1, y, ("v", x + 1, y)),
            (x, y + 1, ("h", x, y + 1)),
        ):
            if (nx, ny) in cell_set and edge not in protected:
                cands.append(edge)
    if not cands:
        return
    edge = random.choice(cands)
    orient, a, b = edge
    if orient == "v":
        for dy in (-1, 0, 1):
            e = ("v", a, b + dy)
            if 0 <= b + dy < h and e not in protected:
                walls.add(e)
    else:
        for dx in (-1, 0, 1):
            e = ("h", a + dx, b)
            if 0 <= a + dx < w and e not in protected:
                walls.add(e)


# ---------------------------------------------------------------------------
# Door flanks
# ---------------------------------------------------------------------------

def _collinear_neighbors(edge, w, h):
    orient, x, y = edge
    out = []
    if orient == "v":
        if y - 1 >= 0:
            out.append(("v", x, y - 1))
        if y + 1 < h:
            out.append(("v", x, y + 1))
    else:
        if x - 1 >= 0:
            out.append(("h", x - 1, y))
        if x + 1 < w:
            out.append(("h", x + 1, y))
    return out


def _door_is_fully_flanked(edge, walls, w, h):
    neighbors = _collinear_neighbors(edge, w, h)
    if len(neighbors) < 2:
        return False
    return all(n in walls for n in neighbors)


def _embed_door_in_wall(walls, edge, w, h):
    if not _is_interior_edge(edge, w, h):
        return False
    neighbors = _collinear_neighbors(edge, w, h)
    if len(neighbors) < 2:
        return False
    walls.discard(edge)
    for n in neighbors:
        walls.add(n)
    walls.discard(edge)
    return _door_is_fully_flanked(edge, walls, w, h)


def _embed_all_doors_in_walls(doors, walls, w, h):
    bad = []
    for edge in list(doors.keys()):
        if not _embed_door_in_wall(walls, edge, w, h):
            bad.append(edge)
        walls.discard(edge)
    return bad


def _all_doors_are_wall_gaps(doors, walls, w, h):
    for edge in doors:
        if edge in walls or not _door_is_fully_flanked(edge, walls, w, h):
            return False
    return True


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _outer_walls_only(w, h):
    walls = set()
    for x in range(w):
        walls.add(("h", x, 0))
        walls.add(("h", x, h))
    for y in range(h):
        walls.add(("v", 0, y))
        walls.add(("v", w, y))
    return walls


def _pick_cell(cells, prefer=None):
    cells = list(cells)
    if not cells:
        return (0, 0)
    if prefer and prefer in cells:
        return prefer
    if prefer:
        return min(cells, key=lambda c: abs(c[0] - prefer[0]) + abs(c[1] - prefer[1]))
    return random.choice(cells)


def _handle_toward(edge, player):
    a, b = _cells_through_edge(edge)
    da = abs(a[0] - player[0]) + abs(a[1] - player[1])
    db = abs(b[0] - player[0]) + abs(b[1] - player[1])
    return "a" if da <= db else "b"


def _cells_through_edge(edge):
    orient, x, y = edge
    if orient == "v":
        return (x - 1, y), (x, y)
    return (x, y - 1), (x, y)


def _is_interior_edge(edge, w, h):
    orient, x, y = edge
    if orient == "v":
        return 0 < x < w
    return 0 < y < h


def _cells_connected(a, b, w, h, walls, open_edges):
    open_edges = set(open_edges or [])
    seen = {a}
    q = deque([a])
    while q:
        x, y = q.popleft()
        if (x, y) == b:
            return True
        for nx, ny, edge in (
            (x + 1, y, ("v", x + 1, y)),
            (x - 1, y, ("v", x, y)),
            (x, y + 1, ("h", x, y + 1)),
            (x, y - 1, ("h", x, y)),
        ):
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if edge in walls and edge not in open_edges:
                continue
            if (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
    return False


def _blocked(edge, walls, doors, door_state_map=None):
    if edge in walls:
        return True
    if edge in doors:
        state = (
            door_state_map[edge]
            if door_state_map is not None
            else doors[edge]["state"]
        )
        return state == 1
    return False


def _neighbors(x, y, w, h, walls, doors, door_state_map=None):
    out = []
    for nx, ny, edge in (
        (x + 1, y, ("v", x + 1, y)),
        (x - 1, y, ("v", x, y)),
        (x, y + 1, ("h", x, y + 1)),
        (x, y - 1, ("h", x, y)),
    ):
        if 0 <= nx < w and 0 <= ny < h and not _blocked(edge, walls, doors, door_state_map):
            out.append((nx, ny))
    return out


def _reachable(start, w, h, walls, doors, door_state_map=None):
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for n in _neighbors(x, y, w, h, walls, doors, door_state_map):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def density_metrics(walls, w, h, doors=None):
    total_int = wall_int = 0
    for y in range(h):
        for x in range(1, w):
            total_int += 1
            if ("v", x, y) in walls:
                wall_int += 1
    for y in range(1, h):
        for x in range(w):
            total_int += 1
            if ("h", x, y) in walls:
                wall_int += 1
    return {
        "wall_ratio": wall_int / total_int if total_int else 0,
        "avg_degree": 0,
        "cells": w * h,
    }


def meets_density(walls, w, h, doors, difficulty):
    return True


def density_score(walls, w, h, doors, difficulty):
    cells = w * h
    score = 200 - cells * 2
    return max(0, score), density_metrics(walls, w, h, doors)
