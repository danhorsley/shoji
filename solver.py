"""Solvability search, solution extraction, and multi-phase quality scoring."""

from collections import deque


def _edge_key(e):
    if isinstance(e, (list, tuple)) and len(e) == 3:
        return (e[0], int(e[1]), int(e[2]))
    return e


def cells_through_edge(edge):
    orient, x, y = edge
    if orient == "v":
        return (x - 1, y), (x, y)  # a, b
    return (x, y - 1), (x, y)


def connected_component(doors, start):
    start = _edge_key(start)
    if start not in doors:
        return []
    seen = {start}
    q = deque([start])
    while q:
        e = q.popleft()
        for link in doors[e].get("linked", []):
            le = _edge_key(link)
            if le in doors and le not in seen:
                seen.add(le)
                q.append(le)
    return list(seen)


def apply_toggle(state_map, doors, edge):
    new = dict(state_map)
    for e in connected_component(doors, edge):
        if e in new:
            new[e] = 1 - new[e]
    return new


def can_activate(doors, edge, player_pos):
    """
    remote  — never by direct click
    local   — either incident cell
    onesided — handle cell only (a=left/top, b=right/bottom)
    """
    edge = _edge_key(edge)
    if edge not in doors:
        return False
    door = doors[edge]
    kind = door.get("kind", "local")
    if kind == "remote":
        return False
    a, b = cells_through_edge(edge)
    if kind == "onesided":
        handle = door.get("handle", "a")
        need = a if handle == "a" else b
        return player_pos == need
    return player_pos in (a, b)


def activatable_doors(doors, player_pos):
    return [e for e in doors if can_activate(doors, e, player_pos)]


def _blocked(edge, walls, state_map):
    if edge in walls:
        return True
    if edge in state_map and state_map[edge] == 1:
        return True
    return False


def _neighbors_walk(x, y, w, h, walls, state_map):
    out = []
    for nx, ny, edge in (
        (x + 1, y, ("v", x + 1, y)),
        (x - 1, y, ("v", x, y)),
        (x, y + 1, ("h", x, y + 1)),
        (x, y - 1, ("h", x, y)),
    ):
        if 0 <= nx < w and 0 <= ny < h and not _blocked(edge, walls, state_map):
            out.append((nx, ny))
    return out


def walk_reachable(start, goal, w, h, walls, state_map):
    """BFS walk-only; return path length or None."""
    if start == goal:
        return 0
    dist = {start: 0}
    q = deque([start])
    while q:
        p = q.popleft()
        x, y = p
        for n in _neighbors_walk(x, y, w, h, walls, state_map):
            if n not in dist:
                dist[n] = dist[p] + 1
                if n == goal:
                    return dist[n]
                q.append(n)
    return None


def all_open_path_cells(game):
    """Cells on a shortest path with every door forced open."""
    w, h = game.width, game.height
    open_map = {e: 0 for e in game.doors}
    start, goal = game.player_pos, game.exit_pos
    parent = {start: None}
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
            if _blocked(edge, game.walls, open_map):
                continue
            if (nx, ny) in parent:
                continue
            parent[(nx, ny)] = (x, y)
            q.append((nx, ny))
    if not found:
        return set()
    cells = set()
    cur = goal
    while cur is not None:
        cells.add(cur)
        cur = parent[cur]
    return cells


def find_solution(game, max_states=300_000):
    """
    Shortest action sequence (BFS) to the exit.
    Returns None or a dict with path metrics and action list.
    Actions: ("move", x, y) | ("toggle", edge)
    """
    w, h = game.width, game.height
    walls = game.walls
    doors = game.doors
    if w <= 0 or h <= 0:
        return None

    start_map = {e: d["state"] for e, d in doors.items()}
    start_pos = (game.player_pos[0], game.player_pos[1])
    goal = game.exit_pos
    start_key = (start_pos[0], start_pos[1], frozenset(start_map.items()))

    # key -> (parent_key, action, state_map_ref for child)
    parent = {start_key: None}
    # store state maps separately
    state_at = {start_key: start_map}
    queue = deque([start_key])
    states = 0
    goal_key = None

    while queue:
        key = queue.popleft()
        x, y, _fs = key
        state_map = state_at[key]
        states += 1
        if states > max_states:
            return None
        if (x, y) == goal:
            goal_key = key
            break

        for nx, ny, edge in (
            (x + 1, y, ("v", x + 1, y)),
            (x - 1, y, ("v", x, y)),
            (x, y + 1, ("h", x, y + 1)),
            (x, y - 1, ("h", x, y)),
        ):
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if _blocked(edge, walls, state_map):
                continue
            nkey = (nx, ny, frozenset(state_map.items()))
            if nkey in parent:
                continue
            parent[nkey] = (key, ("move", nx, ny))
            state_at[nkey] = state_map
            queue.append(nkey)

        for edge in activatable_doors(doors, (x, y)):
            new_map = apply_toggle(state_map, doors, edge)
            nkey = (x, y, frozenset(new_map.items()))
            if nkey in parent:
                continue
            parent[nkey] = (key, ("toggle", edge))
            state_at[nkey] = new_map
            queue.append(nkey)

    if goal_key is None:
        return None

    # Reconstruct
    actions = []
    positions = [goal]
    cur = goal_key
    while parent[cur] is not None:
        pkey, action = parent[cur]
        actions.append(action)
        if action[0] == "move":
            positions.append((pkey[0], pkey[1]))
        cur = pkey
    positions.append(start_pos)
    positions.reverse()
    actions.reverse()

    toggles = [a for a in actions if a[0] == "toggle"]
    moves = [a for a in actions if a[0] == "move"]
    toggle_cells = []
    pos_i = 0
    # track position through actions for toggle locations
    cx, cy = start_pos
    for a in actions:
        if a[0] == "move":
            cx, cy = a[1], a[2]
        else:
            toggle_cells.append((cx, cy))

    return {
        "actions": actions,
        "positions": positions,
        "moves": len(moves),
        "toggles": len(toggles),
        "toggle_cells": toggle_cells,
        "toggle_edges": [a[1] for a in toggles],
    }


def score_solution(info, game):
    """
    Higher = more multi-phase / double-back / detour interest.
    Returns (score: int, details: dict). score -1 if unusable.
    """
    if not info or info["toggles"] < 1:
        return -1, {"reason": "no_toggles"}

    positions = info["positions"]
    revisits = len(positions) - len(set(positions))
    toggles = info["toggles"]
    moves = info["moves"]

    main_cells = all_open_path_cells(game)
    # Side-room / off-spine toggles: operated from a cell not on the all-open spine
    off_spine_toggles = sum(1 for c in info["toggle_cells"] if c not in main_cells)

    # How much longer is the solution walk vs all-open shortest path
    open_map = {e: 0 for e in game.doors}
    open_len = walk_reachable(
        game.player_pos,
        game.exit_pos,
        game.width,
        game.height,
        game.walls,
        open_map,
    )
    detour_extra = 0
    if open_len is not None:
        detour_extra = max(0, moves - open_len)

    # Multi-phase: after first toggle, exit still not walk-reachable (needs more work)
    # Approximate using action log: simulate
    multi_phase = 0
    state_map = {e: d["state"] for e, d in game.doors.items()}
    pos = game.player_pos
    toggles_done = 0
    for a in info["actions"]:
        if a[0] == "move":
            pos = (a[1], a[2])
        else:
            state_map = apply_toggle(state_map, game.doors, a[1])
            toggles_done += 1
            if toggles_done == 1:
                if walk_reachable(
                    pos,
                    game.exit_pos,
                    game.width,
                    game.height,
                    game.walls,
                    state_map,
                ) is None:
                    multi_phase = 1

    score = 0
    score += 12 * toggles
    score += 6 * revisits
    score += 14 * off_spine_toggles
    score += min(20, detour_extra) * 2
    score += 18 * multi_phase
    if toggles >= 2:
        score += 10

    details = {
        "toggles": toggles,
        "revisits": revisits,
        "off_spine_toggles": off_spine_toggles,
        "detour_extra": detour_extra,
        "multi_phase": multi_phase,
        "moves": moves,
        "score": score,
    }
    return score, details


def is_solvable(game, max_states=300_000):
    return find_solution(game, max_states=max_states) is not None


def quality_threshold(difficulty):
    """Minimum score / constraints for a level to be 'interesting enough'."""
    d = max(0, int(difficulty))
    return {
        "min_score": 18 + d * 8,
        "min_toggles": 1 if d < 2 else 2,
        "min_revisits": 1 if d >= 1 else 0,
        "min_off_spine": 1,  # at least one switch-style toggle off the main spine
        # multi_phase preferred at higher difficulty but not hard-required
        # (best-candidate fallback still applies in the game loop)
    }


def meets_quality(score, details, difficulty):
    if score < 0 or not details:
        return False
    t = quality_threshold(difficulty)
    if score < t["min_score"]:
        return False
    if details.get("revisits", 0) < t["min_revisits"]:
        return False
    if details.get("off_spine_toggles", 0) < t["min_off_spine"]:
        return False
    toggles = details.get("toggles", 0)
    if toggles >= t["min_toggles"]:
        return True
    # Alternate path for higher levels: deep double-back can compensate
    # for a single clever toggle when a second chain wasn't placed.
    if (
        difficulty >= 2
        and toggles >= 1
        and details.get("revisits", 0) >= 4
        and details.get("detour_extra", 0) >= 8
    ):
        return True
    return False
