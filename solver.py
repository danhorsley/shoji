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
    Higher = multi-phase, multi-toggle, compact interest.
    Trivial one-toggle open-exit puzzles score poorly / negative flags.
    """
    if not info or info["toggles"] < 1:
        return -1, {"reason": "no_toggles"}

    positions = info["positions"]
    revisits = len(positions) - len(set(positions))
    toggles = info["toggles"]
    moves = info["moves"]

    main_cells = all_open_path_cells(game)
    off_spine_toggles = sum(1 for c in info["toggle_cells"] if c not in main_cells)

    open_map = {e: 0 for e in game.doors}
    open_len = walk_reachable(
        game.player_pos,
        game.exit_pos,
        game.width,
        game.height,
        game.walls,
        open_map,
    )
    detour_extra = max(0, moves - open_len) if open_len is not None else 0

    # How many toggles before exit becomes walk-reachable?
    state_map = {e: d["state"] for e, d in game.doors.items()}
    pos = game.player_pos
    toggles_done = 0
    multi_phase = 0
    phases = 0  # toggles required before exit opens
    exit_open_after = None
    distinct_toggle_cells = set()
    for a in info["actions"]:
        if a[0] == "move":
            pos = (a[1], a[2])
        else:
            state_map = apply_toggle(state_map, game.doors, a[1])
            toggles_done += 1
            distinct_toggle_cells.add(pos)
            if exit_open_after is None:
                if walk_reachable(
                    pos,
                    game.exit_pos,
                    game.width,
                    game.height,
                    game.walls,
                    state_map,
                ) is not None:
                    exit_open_after = toggles_done
                else:
                    multi_phase = 1
    phases = exit_open_after if exit_open_after is not None else toggles

    # Trivial: one toggle and exit immediately walkable after it
    trivial = toggles == 1 and multi_phase == 0

    moves_per_toggle = moves / max(1, toggles)
    chains_used = len({frozenset(connected_component(game.doors, e)) for e in info["toggle_edges"]})

    score = 0
    score += 18 * toggles
    score += 22 * multi_phase
    score += 14 * max(0, phases - 1)
    score += 12 * min(revisits, 5)
    score += 10 * off_spine_toggles
    score += 16 * max(0, chains_used - 1)  # using 2+ chains
    score += 10 * max(0, len(distinct_toggle_cells) - 1)  # toggles from different places

    if trivial:
        score -= 50

    # Compact efficiency
    if moves <= 18:
        score += 18
    elif moves <= 26:
        score += 8
    else:
        score -= min(35, (moves - 26) * 2)

    if moves_per_toggle <= 10:
        score += 14
    elif moves_per_toggle > 14:
        score -= min(25, int((moves_per_toggle - 14) * 3))

    score += min(8, detour_extra)
    cells = max(1, game.width * game.height)
    if cells <= 36:
        score += 12
    elif cells <= 48:
        score += 6

    details = {
        "toggles": toggles,
        "revisits": revisits,
        "off_spine_toggles": off_spine_toggles,
        "detour_extra": detour_extra,
        "multi_phase": multi_phase,
        "phases": phases,
        "trivial": trivial,
        "chains_used": chains_used,
        "toggle_sites": len(distinct_toggle_cells),
        "moves": moves,
        "moves_per_toggle": round(moves_per_toggle, 2),
        "score": score,
    }
    return score, details


def is_solvable(game, max_states=300_000):
    return find_solution(game, max_states=max_states) is not None


def is_trivial_solution(details):
    if not details:
        return True
    if details.get("trivial"):
        return True
    # Single toggle, exit opens immediately, one site
    if details.get("toggles", 0) <= 1 and details.get("multi_phase", 0) == 0:
        return True
    return False


def quality_threshold(difficulty):
    """
    Curate-worthy bar: multi-phase or multi-toggle, not a one-click hallway.
    Aim ~1 interesting level per handful of candidates (strict filter).
    """
    d = max(0, int(difficulty))
    return {
        "min_score": 55 + d * 5,
        "min_toggles": 2,  # at least two flips in optimal solution
        "min_revisits": 1,
        "require_multi_phase": True,  # first toggle alone shouldn't clear exit
        "max_moves": 28 + min(6, d),
        "max_moves_per_toggle": 14,
    }


def meets_quality(score, details, difficulty):
    """Strict gate for playable / curatable levels."""
    if score < 0 or not details:
        return False
    if is_trivial_solution(details):
        return False
    t = quality_threshold(difficulty)
    moves = details.get("moves", 999)
    toggles = details.get("toggles", 0)
    mpt = details.get("moves_per_toggle", moves / max(1, toggles))

    if moves > t["max_moves"]:
        return False
    if mpt > t["max_moves_per_toggle"]:
        return False
    if score < t["min_score"]:
        return False
    if toggles < t["min_toggles"]:
        return False
    if details.get("revisits", 0) < t["min_revisits"]:
        return False
    if t.get("require_multi_phase") and not details.get("multi_phase"):
        # Allow rare alternative: 2+ chains used even if solver order opens early
        if details.get("chains_used", 0) < 2 or toggles < 2:
            return False
    return True


def meets_curate_quality(score, details, difficulty):
    """Slightly higher bar when auto-hunting for curated set."""
    if not meets_quality(score, details, difficulty):
        return False
    # Prefer true multi-phase + two toggle sites
    if details.get("multi_phase") and details.get("toggle_sites", 0) >= 2:
        return True
    if details.get("chains_used", 0) >= 2 and details.get("toggles", 0) >= 2:
        return score >= 60 + max(0, int(difficulty)) * 4
    return False
