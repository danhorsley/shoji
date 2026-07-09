"""
Room-first / switch-room maze generation.

Biased toward multi-phase puzzles:
  entry  →  side switch room (local / one-way control)
         →  backtrack
         →  exit wing (remote door opened by the switch chain)

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
        w = min(10 + difficulty // 2, 14)
    if h is None:
        h = min(7 + difficulty // 2, 11)

    # Prefer structured switch-room template; fall back to division maze
    if random.random() < 0.85:
        result = _generate_switch_template(w, h, difficulty)
        if result is not None:
            return result
    return _generate_division_fallback(w, h, difficulty)


# ---------------------------------------------------------------------------
# Switch-room template (primary)
# ---------------------------------------------------------------------------

def _generate_switch_template(w, h, difficulty):
    """
    Layout (example):

        +--------+----------+
        | SWITCH |          |
        |  [ctrl]|   EXIT   |
        +---gap--+   WING   |
        | ENTRY  |          |
        | start  |   exit   |
        +--------+----------+

    - Open gap into SWITCH (or local door that starts open)
    - Control shoji in SWITCH (local or one-way from inside)
    - REMOTE door on cut into EXIT wing, same chain, opposite polarity
    - Optional second remote / chain at higher difficulty
    """
    if w < 8 or h < 6:
        w, h = max(w, 8), max(h, 6)

    walls = _outer_walls_only(w, h)

    # Partition lines
    vx = max(3, min(w // 2, w - 4))  # vertical cut: left living / right exit
    hy = max(2, min(h // 2, h - 3))  # horizontal cut on left: switch / entry

    # Vertical partition (entry+switch | exit wing)
    for y in range(h):
        walls.add(("v", vx, y))

    # Horizontal partition on left only (switch above, entry below)
    for x in range(vx):
        walls.add(("h", x, hy))

    # --- Gaps / doors ---
    # Switch entry: open gap near middle of horizontal wall (no door → free enter/leave)
    sw_gap_x = max(1, min(vx - 2, vx // 2))
    walls.discard(("h", sw_gap_x, hy))

    # Exit cut: remote door on vertical partition (lower half = from entry)
    exit_door_y = min(h - 2, max(hy, hy + (h - hy) // 2))
    # Prefer a cell-row entirely in the entry band when possible
    exit_door_y = random.randint(hy, h - 1) if hy < h - 1 else h - 2
    walls.discard(("v", vx, exit_door_y))
    exit_remote = ("v", vx, exit_door_y)

    # Optional second gap into exit wing from switch (usually walled — forces return)
    # Leave sealed for double-back; at low difficulty sometimes open as red herring wall gap
    if difficulty == 0 and random.random() < 0.15:
        y2 = random.randint(0, max(0, hy - 1))
        walls.discard(("v", vx, y2))

    # Control door: small alcove inside switch room
    # Place a short wall with a door edge inside switch (y < hy, x < vx)
    ctrl = _place_switch_control(walls, vx, hy, w, h)
    if ctrl is None:
        return None

    # Player in entry, exit in exit wing
    player = (max(1, sw_gap_x - 1), min(h - 2, hy + 1))
    # Ensure player cell not in wall (cells are all open; walls are edges)
    if player[0] >= vx:
        player = (vx - 2, player[1])
    if player[1] < hy:
        player = (player[0], hy)

    exit_pos = (min(w - 2, vx + 1 + random.randint(0, max(0, w - vx - 3))), random.randint(1, h - 2))
    if exit_pos[0] < vx:
        exit_pos = (vx + 1, exit_pos[1])

    # Connectivity check with exit open
    if not _cells_connected(player, exit_pos, w, h, walls, {exit_remote, ctrl}):
        # try alternate exit placement
        exit_pos = (w - 2, h // 2)
        if not _cells_connected(player, exit_pos, w, h, walls, {exit_remote, ctrl}):
            return None

    doors = {}
    # Primary chain: switch control <-> exit remote (opposite polarity)
    doors[ctrl] = {
        "state": 0,  # open — doesn't block alcove awkwardly
        "linked": [list(exit_remote)],
        "kind": "local",
        "handle": "a",
    }
    doors[exit_remote] = {
        "state": 1,  # closed — must use switch
        "linked": [list(ctrl)],
        "kind": "remote",
        "handle": "a",
    }

    # Control often one-way from inside switch (must enter room first)
    if random.random() < 0.55 + difficulty * 0.1:
        doors[ctrl]["kind"] = "onesided"
        # Handle toward switch interior centroid
        switch_centroid = (max(0, vx // 2), max(0, hy // 2))
        doors[ctrl]["handle"] = _handle_toward(ctrl, switch_centroid)

    # Extra spice by difficulty
    _add_secondary_chain(doors, walls, w, h, vx, hy, player, exit_pos, difficulty)

    # Texture: a few extra permanent walls in exit wing / entry (not sealing)
    _add_texture_walls(walls, w, h, vx, hy, player, exit_pos, doors)

    # Ensure player not sealed at start
    state_map = {e: d["state"] for e, d in doors.items()}
    if len(_neighbors(*player, w, h, walls, doors, state_map)) == 0:
        return None

    # Must be walk-blocked to exit at start
    if exit_pos in _reachable(player, w, h, walls, doors, state_map):
        # force exit remote closed
        doors[exit_remote]["state"] = 1
        # keep opposite relative to ctrl if linked
        # (ctrl open / remote closed is already opposite)
        state_map = {e: doors[e]["state"] for e in doors}
        if exit_pos in _reachable(player, w, h, walls, doors, state_map):
            return None

    return w, h, walls, player, exit_pos, doors


def _place_switch_control(walls, vx, hy, w, h):
    """
    Interior edge fully inside the switch region [0,vx) x [0,hy).

    This is a stand-next-to control panel: both sides stay in the open switch
    room so closing the door never softlocks the player (they walk around).
    """
    if hy < 2 or vx < 3:
        return None

    candidates = []
    for ax in range(1, vx):
        for ay in range(0, hy):
            e = ("v", ax, ay)
            if e not in walls:
                candidates.append(e)
    for ax in range(0, vx):
        for ay in range(1, hy):
            e = ("h", ax, ay)
            if e not in walls:
                candidates.append(e)
    if not candidates:
        return None
    return random.choice(candidates)


def _add_secondary_chain(doors, walls, w, h, vx, hy, player, exit_pos, difficulty):
    """Second chain for multi-toggle phases at higher difficulty."""
    if difficulty < 2:
        return
    # Always try at difficulty 2+; success depends on available passages

    # Place another remote on a path edge in exit wing + local in entry
    passages = [e for e in _all_passages(w, h, walls) if e not in doors and _is_interior_edge(e, w, h)]
    if len(passages) < 2:
        return

    # Prefer edges near exit vs near player
    def mid(e):
        o, x, y = e
        return (x, y) if o == "v" else (x, y)

    random.shuffle(passages)
    remote_e = None
    local_e = None
    for e in passages:
        c1, c2 = _cells_through_edge(e)
        if min(c1[0], c2[0]) >= vx:
            remote_e = e
            break
    for e in passages:
        if e == remote_e:
            continue
        c1, c2 = _cells_through_edge(e)
        if max(c1[0], c2[0]) < vx and min(c1[1], c2[1]) >= hy:
            local_e = e
            break
    if remote_e is None or local_e is None:
        return

    doors[remote_e] = {
        "state": 1,
        "linked": [list(local_e)],
        "kind": "remote",
        "handle": "a",
    }
    doors[local_e] = {
        "state": 0,
        "linked": [list(remote_e)],
        "kind": "onesided" if random.random() < 0.5 else "local",
        "handle": _handle_toward(local_e, player),
    }


def _add_texture_walls(walls, w, h, vx, hy, player, exit_pos, doors):
    """Scatter a few permanent walls that don't disconnect critical cells."""
    open_doors = set(doors.keys())
    candidates = []
    for y in range(h):
        for x in range(1, w):
            e = ("v", x, y)
            if e not in walls and e not in open_doors:
                candidates.append(e)
    for y in range(1, h):
        for x in range(w):
            e = ("h", x, y)
            if e not in walls and e not in open_doors:
                candidates.append(e)
    random.shuffle(candidates)
    added = 0
    for e in candidates:
        if added >= random.randint(2, 5):
            break
        walls.add(e)
        # revert if we disconnect player from switch gap or exit cells
        if not _cells_connected(player, exit_pos, w, h, walls, open_doors):
            walls.discard(e)
            continue
        added += 1


def _cells_connected(a, b, w, h, walls, open_edges):
    """Treat open_edges as non-walls (passable)."""
    blocked = set(walls)
    # open_edges are passable
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
            if edge in blocked and edge not in open_edges:
                continue
            if (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
    return False


def _outer_walls_only(w, h):
    walls = set()
    for x in range(w):
        walls.add(("h", x, 0))
        walls.add(("h", x, h))
    for y in range(h):
        walls.add(("v", 0, y))
        walls.add(("v", w, y))
    return walls


# ---------------------------------------------------------------------------
# Division fallback (secondary)
# ---------------------------------------------------------------------------

def _generate_division_fallback(w, h, difficulty):
    walls, door_slots = _room_division_maze(w, h, difficulty)
    doors = {}
    player, exit_pos = _farthest_pair(w, h, walls, doors)

    slots = [e for e in door_slots if _is_interior_edge(e, w, h)]
    if len(slots) < 3:
        slots = [e for e in _all_passages(w, h, walls) if _is_interior_edge(e, w, h)]

    path_edges = _shortest_path_edges(player, exit_pos, w, h, walls, {}, {})
    path_set = set(path_edges)
    path_slots = [e for e in slots if e in path_set and not _edge_touches_cell(e, player)]
    off_slots = [e for e in slots if e not in path_set]
    random.shuffle(path_slots)
    random.shuffle(off_slots)

    # Force at least one path remote + one off-path local, linked
    if not path_slots or not off_slots:
        # degrade gracefully
        path_slots = path_slots or slots[:1]
        off_slots = off_slots or slots[1:2]

    exit_remote = path_slots[0]
    switch_local = off_slots[0]
    extra_path = path_slots[1:1 + difficulty // 2]
    extra_off = off_slots[1:2 + difficulty]

    for e in [exit_remote, switch_local] + extra_path + extra_off:
        doors[e] = {"state": 0, "linked": [], "kind": "local", "handle": "a"}

    doors[exit_remote]["kind"] = "remote"
    doors[exit_remote]["state"] = 1
    doors[switch_local]["state"] = 0
    doors[switch_local]["kind"] = "onesided"
    doors[switch_local]["handle"] = _handle_toward(switch_local, player)
    _link(doors, exit_remote, switch_local)

    # Build additional chains from leftovers
    pool = [e for e in doors if e not in (exit_remote, switch_local)]
    random.shuffle(pool)
    while len(pool) >= 2:
        a, b = pool.pop(), pool.pop()
        _link(doors, a, b)
        doors[a]["state"] = random.choice([0, 1])
        doors[b]["state"] = 1 - doors[a]["state"]
        if random.random() < 0.4:
            doors[a]["kind"] = "remote"
        if random.random() < 0.4 and doors[b]["kind"] != "remote":
            doors[b]["kind"] = "onesided"
            doors[b]["handle"] = _handle_toward(b, player)

    state_map = {e: doors[e]["state"] for e in doors}
    if exit_pos in _reachable(player, w, h, walls, doors, state_map):
        doors[exit_remote]["state"] = 1

    state_map = {e: doors[e]["state"] for e in doors}
    if len(_neighbors(*player, w, h, walls, doors, state_map)) == 0:
        _flip_component(doors, switch_local)

    return w, h, walls, player, exit_pos, doors


def _room_division_maze(w, h, difficulty):
    walls = _full_wall_set(w, h)
    for y in range(h):
        for x in range(1, w):
            walls.discard(("v", x, y))
    for y in range(1, h):
        for x in range(w):
            walls.discard(("h", x, y))

    door_slots = []

    def divide(x0, y0, x1, y1, depth):
        cw, ch = x1 - x0, y1 - y0
        min_size = 2
        if cw < min_size * 2 and ch < min_size * 2:
            return
        if cw < min_size or ch < min_size:
            return
        if cw > ch:
            horiz = False
        elif ch > cw:
            horiz = True
        else:
            horiz = random.choice([True, False])

        if not horiz and cw >= min_size * 2:
            split = random.randrange(x0 + min_size, x1 - min_size + 1)
            gaps = max(1, 1 + (1 if difficulty < 2 else 0))
            gap_rows = random.sample(range(y0, y1), k=min(gaps, y1 - y0))
            for y in range(y0, y1):
                e = ("v", split, y)
                if y in gap_rows:
                    door_slots.append(e)
                else:
                    walls.add(e)
            divide(x0, y0, split, y1, depth + 1)
            divide(split, y0, x1, y1, depth + 1)
        elif horiz and ch >= min_size * 2:
            split = random.randrange(y0 + min_size, y1 - min_size + 1)
            gaps = max(1, 1 + (1 if difficulty < 2 else 0))
            gap_cols = random.sample(range(x0, x1), k=min(gaps, x1 - x0))
            for x in range(x0, x1):
                e = ("h", x, split)
                if x in gap_cols:
                    door_slots.append(e)
                else:
                    walls.add(e)
            divide(x0, y0, x1, split, depth + 1)
            divide(x0, split, x1, y1, depth + 1)

    divide(0, 0, w, h, 0)
    door_slots = [e for e in dict.fromkeys(door_slots) if e not in walls]
    return walls, door_slots


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _link(doors, a, b):
    if a == b:
        return
    if list(b) not in doors[a]["linked"]:
        doors[a]["linked"].append(list(b))
    if list(a) not in doors[b]["linked"]:
        doors[b]["linked"].append(list(a))


def _handle_toward(edge, player):
    a, b = _cells_through_edge(edge)
    da = abs(a[0] - player[0]) + abs(a[1] - player[1])
    db = abs(b[0] - player[0]) + abs(b[1] - player[1])
    return "a" if da <= db else "b"


def _flip_component(doors, edge):
    edge = _norm_edge(edge)
    stack = [edge]
    seen = {edge}
    while stack:
        e = stack.pop()
        if e not in doors:
            continue
        doors[e]["state"] = 1 - doors[e]["state"]
        for link in doors[e].get("linked", []):
            le = _norm_edge(link)
            if le not in seen and le in doors:
                seen.add(le)
                stack.append(le)


def _full_wall_set(w, h):
    walls = set()
    for y in range(h):
        for x in range(w + 1):
            walls.add(("v", x, y))
    for y in range(h + 1):
        for x in range(w):
            walls.add(("h", x, y))
    return walls


def _is_interior_edge(edge, w, h):
    orient, x, y = edge
    if orient == "v":
        return 0 < x < w
    return 0 < y < h


def _all_passages(w, h, walls):
    passages = []
    for y in range(h):
        for x in range(1, w):
            e = ("v", x, y)
            if e not in walls:
                passages.append(e)
    for y in range(1, h):
        for x in range(w):
            e = ("h", x, y)
            if e not in walls:
                passages.append(e)
    return passages


def _edge_touches_cell(edge, cell):
    return cell in _cells_through_edge(edge)


def _cells_through_edge(edge):
    orient, x, y = edge
    if orient == "v":
        return (x - 1, y), (x, y)
    return (x, y - 1), (x, y)


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


def _farthest_pair(w, h, walls, doors):
    open_map = {e: 0 for e in doors}
    best = None
    samples = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    samples += [(random.randrange(w), random.randrange(h)) for _ in range(5)]
    for s in samples:
        dist = {s: 0}
        q = deque([s])
        far = s
        while q:
            x, y = q.popleft()
            if dist[(x, y)] >= dist[far]:
                far = (x, y)
            for n in _neighbors(x, y, w, h, walls, doors, open_map):
                if n not in dist:
                    dist[n] = dist[(x, y)] + 1
                    q.append(n)
        d = dist.get(far, 0)
        if best is None or d > best[0]:
            best = (d, s, far)
    if best is None or best[0] < 2:
        return (0, 0), (w - 1, h - 1)
    return best[1], best[2]


def _norm_edge(e):
    if isinstance(e, (list, tuple)) and len(e) == 3:
        return (e[0], int(e[1]), int(e[2]))
    return e


def _shortest_path_edges(start, goal, w, h, walls, doors, door_state_map):
    parent = {start: None}
    edge_used = {}
    q = deque([start])
    found = False
    while q:
        x, y = q.popleft()
        if (x, y) == goal:
            found = True
            break
        for nx, ny, edge in (
            (x + 1, y, ("v", x + 1, y)),
            (x - 1, y, ("v", x, y)),
            (x, y + 1, ("h", x, y + 1)),
            (x, y - 1, ("h", x, y)),
        ):
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if _blocked(edge, walls, doors, door_state_map):
                continue
            if (nx, ny) in parent:
                continue
            parent[(nx, ny)] = (x, y)
            edge_used[(nx, ny)] = edge
            q.append((nx, ny))
    if not found:
        return []
    edges = []
    cur = goal
    while parent[cur] is not None:
        edges.append(edge_used[cur])
        cur = parent[cur]
    return edges
