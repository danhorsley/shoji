import ast
import json
import os
from collections import deque

import pygame

from level_generator import generate_level
from solver import (
    apply_toggle,
    can_activate,
    connected_component,
    find_solution,
    is_solvable,
    meets_quality,
    score_solution,
)

TILE_SIZE = 52
WALL_THICKNESS = 5
DOOR_THICKNESS = 10
DOOR_CLICK_PAD = 14
PANEL_WIDTH = 248
HUD_HEIGHT = 56

# Scene colors
BG = (22, 26, 32)
FLOOR = (186, 150, 100)
FLOOR_ALT = (176, 140, 92)
WALL = (72, 48, 32)
WALL_DARK = (48, 32, 20)
SHOJI_PAPER = (238, 228, 208)
SHOJI_PAPER_OPEN = (210, 200, 180)
SHOJI_LATTICE = (150, 128, 100)
PLAYER = (255, 100, 100)
EXIT = (100, 220, 120)
HUD = (200, 200, 200)
PANEL_BG = (18, 20, 26)
PANEL_BORDER = (55, 60, 72)
PANEL_TEXT = (210, 210, 215)
PANEL_MUTED = (140, 145, 155)

# Chain colors (dictionary + door frames)
CHAIN_COLORS = [
    (70, 145, 230),   # blue
    (230, 100, 90),   # coral
    (70, 195, 130),   # green
    (220, 175, 55),   # gold
    (175, 105, 210),  # purple
    (70, 195, 205),   # cyan
    (235, 140, 70),   # orange
    (200, 120, 160),  # rose
]

KIND_LABEL = {
    "local": "Local",
    "remote": "Remote",
    "onesided": "One-way",
}


def edge_key(e):
    if isinstance(e, str):
        e = ast.literal_eval(e)
    return (e[0], int(e[1]), int(e[2]))


def normalize_door(d):
    return {
        "state": int(d.get("state", 0)),
        "linked": [edge_key(L) for L in d.get("linked", [])],
        "kind": d.get("kind", "local"),
        "handle": d.get("handle", "a"),
    }


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.current_level = 0
        self.width = 0
        self.height = 0
        self.walls = set()
        self.player_pos = (0, 0)
        self.exit_pos = (0, 0)
        self.doors = {}
        self.font = pygame.font.SysFont(None, 24)
        self.font_sm = pygame.font.SysFont(None, 20)
        self.font_tiny = pygame.font.SysFont(None, 18)
        self.message = ""
        self.status = ""  # click feedback
        self.chain_ids = {}  # edge -> chain index
        self.chain_list = []  # list of components

    # --- layout -----------------------------------------------------------

    def maze_pixel_size(self):
        return self.width * TILE_SIZE, self.height * TILE_SIZE

    def preferred_window_size(self):
        mw, mh = self.maze_pixel_size()
        return max(mw + PANEL_WIDTH + 8, 640), max(mh + HUD_HEIGHT, 420)

    # --- load / save ------------------------------------------------------

    def load_or_generate_level(self, level_num):
        self.current_level = level_num
        self.message = ""
        self.status = ""
        path = f"levels/level_{level_num}.json"
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if not self._is_valid_level_data(data):
                print(f"Level {level_num} is outdated/invalid; regenerating...")
                self._generate_until_solvable(level_num)
                return
            self._load_from_data(data)
        except FileNotFoundError:
            self._generate_until_solvable(level_num)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Level {level_num} failed to load ({exc}); regenerating...")
            self._generate_until_solvable(level_num)
        self._rebuild_chains()

    @staticmethod
    def _is_valid_level_data(data):
        if not isinstance(data, dict):
            return False
        for k in ("width", "height", "player", "exit", "walls"):
            if k not in data:
                return False
        return True

    def _generate_until_solvable(self, level_num, attempts=80):
        """
        Generate until solvable + multi-phase quality:
        detour / double-back / off-spine switch toggles.
        Keeps the best-scoring candidate if thresholds are never fully met.
        """
        best = None  # (score, snapshot, details)
        difficulty = level_num

        for i in range(attempts):
            w, h, walls, player, exit_pos, doors = generate_level(level_num=level_num)
            self.width = w
            self.height = h
            self.walls = walls
            self.player_pos = player
            self.exit_pos = exit_pos
            self.doors = {edge_key(e): normalize_door(d) for e, d in doors.items()}
            self._rebuild_chains()

            if self._exit_reachable_without_toggles():
                continue

            info = find_solution(self)
            if info is None:
                continue

            score, details = score_solution(info, self)
            if score < 0:
                continue

            snap = self._snapshot()
            if best is None or score > best[0]:
                best = (score, snap, details)
                print(
                    f"  candidate score={score} toggles={details.get('toggles')} "
                    f"revisits={details.get('revisits')} "
                    f"off_spine={details.get('off_spine_toggles')} "
                    f"multi_phase={details.get('multi_phase')}"
                )

            if meets_quality(score, details, difficulty):
                print(f"Level {level_num}: accepted quality score={score} ({details})")
                self.save_level()
                return

        if best is not None:
            print(
                f"Level {level_num}: using best candidate score={best[0]} "
                f"({best[2]}) after {attempts} tries"
            )
            self._restore(best[1])
        else:
            print(f"Level {level_num}: fallback raw generate (no scored solution)")
            w, h, walls, player, exit_pos, doors = generate_level(level_num=level_num)
            self.width = w
            self.height = h
            self.walls = walls
            self.player_pos = player
            self.exit_pos = exit_pos
            self.doors = {edge_key(e): normalize_door(d) for e, d in doors.items()}
            self._rebuild_chains()
        self.save_level()

    def _snapshot(self):
        return {
            "width": self.width,
            "height": self.height,
            "walls": set(self.walls),
            "player": self.player_pos,
            "exit": self.exit_pos,
            "doors": {
                e: {
                    "state": d["state"],
                    "linked": list(d["linked"]),
                    "kind": d["kind"],
                    "handle": d["handle"],
                }
                for e, d in self.doors.items()
            },
        }

    def _restore(self, snap):
        self.width = snap["width"]
        self.height = snap["height"]
        self.walls = set(snap["walls"])
        self.player_pos = snap["player"]
        self.exit_pos = snap["exit"]
        self.doors = {
            e: {
                "state": d["state"],
                "linked": list(d["linked"]),
                "kind": d["kind"],
                "handle": d["handle"],
            }
            for e, d in snap["doors"].items()
        }
        self._rebuild_chains()

    def _exit_reachable_without_toggles(self):
        start = self.player_pos
        goal = self.exit_pos
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            if (x, y) == goal:
                return True
            for nx, ny, edge in (
                (x + 1, y, ("v", x + 1, y)),
                (x - 1, y, ("v", x, y)),
                (x, y + 1, ("h", x, y + 1)),
                (x, y - 1, ("h", x, y)),
            ):
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                if edge in self.walls:
                    continue
                if edge in self.doors and self.doors[edge]["state"] == 1:
                    continue
                if (nx, ny) not in seen:
                    seen.add((nx, ny))
                    q.append((nx, ny))
        return False

    def _load_from_data(self, data):
        self.width = int(data["width"])
        self.height = int(data["height"])
        self.player_pos = tuple(data["player"])
        self.exit_pos = tuple(data["exit"])
        self.walls = {edge_key(e) for e in data.get("walls", [])}
        self.doors = {
            edge_key(k): normalize_door(v) for k, v in data.get("doors", {}).items()
        }
        self._rebuild_chains()

    def save_level(self):
        data = {
            "width": self.width,
            "height": self.height,
            "player": list(self.player_pos),
            "exit": list(self.exit_pos),
            "walls": [list(e) for e in sorted(self.walls)],
            "doors": {
                str(k): {
                    "state": v["state"],
                    "linked": [list(p) for p in v.get("linked", [])],
                    "kind": v.get("kind", "local"),
                    "handle": v.get("handle", "a"),
                }
                for k, v in self.doors.items()
            },
        }
        os.makedirs("levels", exist_ok=True)
        with open(f"levels/level_{self.current_level}.json", "w") as f:
            json.dump(data, f, indent=2)

    def _rebuild_chains(self):
        self.chain_ids = {}
        self.chain_list = []
        seen = set()
        for e in self.doors:
            if e in seen:
                continue
            comp = connected_component(self.doors, e)
            # stable order
            comp = sorted(comp)
            idx = len(self.chain_list)
            self.chain_list.append(comp)
            for de in comp:
                self.chain_ids[de] = idx
                seen.add(de)

    def chain_color(self, edge):
        idx = self.chain_ids.get(edge, 0)
        return CHAIN_COLORS[idx % len(CHAIN_COLORS)]

    # --- interaction ------------------------------------------------------

    def handle_click(self, pos):
        mx, my = pos
        # Ignore clicks on the dictionary panel
        maze_w = self.width * TILE_SIZE
        if mx >= maze_w:
            return
        edge = self._door_at_pixel(mx, my)
        if edge is None:
            return
        if not can_activate(self.doors, edge, self.player_pos):
            kind = self.doors[edge].get("kind", "local")
            if kind == "remote":
                self.status = "Remote door — only moves via its chain color"
            elif kind == "onesided":
                self.status = "One-way — stand on the arrow side to use"
            else:
                self.status = "Stand next to this door to slide it"
            return
        self.toggle_door(edge)
        self.status = "Chain toggled"

    def toggle_door(self, edge):
        edge = edge_key(edge)
        if edge not in self.doors:
            return
        state_map = {e: d["state"] for e, d in self.doors.items()}
        new_map = apply_toggle(state_map, self.doors, edge)
        for e, state in new_map.items():
            self.doors[e]["state"] = state

    def handle_move(self, dx, dy):
        x, y = self.player_pos
        nx, ny = x + dx, y + dy
        if not (0 <= nx < self.width and 0 <= ny < self.height):
            return
        edge = self._edge_between((x, y), (nx, ny))
        if edge is None:
            return
        if edge in self.walls:
            return
        if edge in self.doors and self.doors[edge]["state"] == 1:
            return
        self.player_pos = (nx, ny)
        self.status = ""

    @staticmethod
    def _edge_between(a, b):
        ax, ay = a
        bx, by = b
        if ay == by and abs(ax - bx) == 1:
            return ("v", max(ax, bx), ay)
        if ax == bx and abs(ay - by) == 1:
            return ("h", ax, max(ay, by))
        return None

    def _door_at_pixel(self, mx, my):
        best = None
        best_d = DOOR_CLICK_PAD + 1
        for edge in self.doors:
            d = self._dist_to_edge(mx, my, edge)
            if d < best_d:
                best_d = d
                best = edge
        return best

    def _dist_to_edge(self, mx, my, edge):
        orient, x, y = edge
        if orient == "v":
            sx = x * TILE_SIZE
            y0, y1 = y * TILE_SIZE, (y + 1) * TILE_SIZE
            if my < y0:
                return ((mx - sx) ** 2 + (my - y0) ** 2) ** 0.5
            if my > y1:
                return ((mx - sx) ** 2 + (my - y1) ** 2) ** 0.5
            return abs(mx - sx)
        sy = y * TILE_SIZE
        x0, x1 = x * TILE_SIZE, (x + 1) * TILE_SIZE
        if mx < x0:
            return ((mx - x0) ** 2 + (my - sy) ** 2) ** 0.5
        if mx > x1:
            return ((mx - x1) ** 2 + (my - sy) ** 2) ** 0.5
        return abs(my - sy)

    def update(self):
        if self.player_pos == self.exit_pos:
            self.message = "Level complete!"
            print("Level Complete!")
            self.next_level()

    def next_level(self):
        self.load_or_generate_level(self.current_level + 1)

    # --- drawing ----------------------------------------------------------

    def draw(self):
        self.screen.fill(BG)
        self._draw_maze()
        self._draw_panel()
        self._draw_hud()

    def _draw_maze(self):
        for y in range(self.height):
            for x in range(self.width):
                color = FLOOR if (x + y) % 2 == 0 else FLOOR_ALT
                pygame.draw.rect(
                    self.screen,
                    color,
                    (x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE),
                )

        grid_c = (160, 128, 84)
        for y in range(self.height + 1):
            pygame.draw.line(
                self.screen,
                grid_c,
                (0, y * TILE_SIZE),
                (self.width * TILE_SIZE, y * TILE_SIZE),
                1,
            )
        for x in range(self.width + 1):
            pygame.draw.line(
                self.screen,
                grid_c,
                (x * TILE_SIZE, 0),
                (x * TILE_SIZE, self.height * TILE_SIZE),
                1,
            )

        for edge in self.walls:
            self._draw_wall_line(edge)

        for edge, door in self.doors.items():
            self._draw_shoji(edge, door)

        ex, ey = self.exit_pos
        pygame.draw.rect(
            self.screen,
            EXIT,
            (
                ex * TILE_SIZE + TILE_SIZE // 4,
                ey * TILE_SIZE + TILE_SIZE // 4,
                TILE_SIZE // 2,
                TILE_SIZE // 2,
            ),
            border_radius=4,
        )

        px, py = self.player_pos
        pygame.draw.circle(
            self.screen,
            PLAYER,
            (px * TILE_SIZE + TILE_SIZE // 2, py * TILE_SIZE + TILE_SIZE // 2),
            max(11, TILE_SIZE // 4),
        )

        # Highlight doors the player can currently activate
        for edge in self.doors:
            if can_activate(self.doors, edge, self.player_pos):
                self._draw_activatable_glow(edge)

    def _draw_activatable_glow(self, edge):
        orient, x, y = edge
        col = self.chain_color(edge)
        if orient == "v":
            sx = x * TILE_SIZE
            y0, y1 = y * TILE_SIZE + 2, (y + 1) * TILE_SIZE - 2
            pygame.draw.line(self.screen, col, (sx, y0), (sx, y1), 2)
        else:
            sy = y * TILE_SIZE
            x0, x1 = x * TILE_SIZE + 2, (x + 1) * TILE_SIZE - 2
            pygame.draw.line(self.screen, col, (x0, sy), (x1, sy), 2)

    def _draw_wall_line(self, edge):
        orient, x, y = edge
        if orient == "v":
            sx = x * TILE_SIZE
            y0, y1 = y * TILE_SIZE, (y + 1) * TILE_SIZE
            pygame.draw.line(self.screen, WALL_DARK, (sx, y0), (sx, y1), WALL_THICKNESS + 2)
            pygame.draw.line(self.screen, WALL, (sx, y0), (sx, y1), WALL_THICKNESS)
        else:
            sy = y * TILE_SIZE
            x0, x1 = x * TILE_SIZE, (x + 1) * TILE_SIZE
            pygame.draw.line(self.screen, WALL_DARK, (x0, sy), (x1, sy), WALL_THICKNESS + 2)
            pygame.draw.line(self.screen, WALL, (x0, sy), (x1, sy), WALL_THICKNESS)

    def _draw_shoji(self, edge, door):
        orient, x, y = edge
        closed = door["state"] == 1
        paper = SHOJI_PAPER if closed else SHOJI_PAPER_OPEN
        kind = door.get("kind", "local")
        chain_col = self.chain_color(edge)
        t = DOOR_THICKNESS
        # Remote doors: slightly darker paper
        if kind == "remote":
            paper = tuple(max(0, c - 35) for c in paper)

        if orient == "v":
            cx = x * TILE_SIZE
            y0 = y * TILE_SIZE + 3
            y1 = (y + 1) * TILE_SIZE - 3
            full_h = y1 - y0
            if closed:
                rect = pygame.Rect(cx - t // 2, y0, t, full_h)
            else:
                rect = pygame.Rect(cx - t // 2, y0, t, max(t + 4, full_h // 3))
        else:
            cy = y * TILE_SIZE
            x0 = x * TILE_SIZE + 3
            x1 = (x + 1) * TILE_SIZE - 3
            full_w = x1 - x0
            if closed:
                rect = pygame.Rect(x0, cy - t // 2, full_w, t)
            else:
                rect = pygame.Rect(x0, cy - t // 2, max(t + 4, full_w // 3), t)

        # Frame uses chain color
        pygame.draw.rect(self.screen, chain_col, rect.inflate(2, 2), border_radius=2)
        frame = tuple(max(0, c - 40) for c in chain_col)
        pygame.draw.rect(self.screen, frame, rect, border_radius=2)
        inner = rect.inflate(-3, -3)
        if inner.width > 1 and inner.height > 1:
            pygame.draw.rect(self.screen, paper, inner, border_radius=1)
            self._draw_lattice(inner, orient)

        self._draw_kind_badge(kind, door, edge)

    def _draw_kind_badge(self, kind, door, edge):
        """
        Badges sit in world space relative to the edge.
        One-way arrows are drawn *inside the handle cell*, tip toward the door,
        matching can_activate: handle 'a' = left/top cell, 'b' = right/bottom.
        """
        orient, x, y = edge
        col = self.chain_color(edge)
        pad = DOOR_THICKNESS // 2 + 9

        if orient == "v":
            wall_x = x * TILE_SIZE
            mid_y = y * TILE_SIZE + TILE_SIZE // 2
            if kind == "onesided":
                handle = door.get("handle", "a")
                # Arrow lives on the usable side, points at the wall line
                if handle == "a":  # left cell (x-1)
                    tip = (wall_x - 3, mid_y)
                    base_x = wall_x - 14
                    pts = [tip, (base_x, mid_y - 7), (base_x, mid_y + 7)]
                else:  # right cell (x)
                    tip = (wall_x + 3, mid_y)
                    base_x = wall_x + 14
                    pts = [tip, (base_x, mid_y - 7), (base_x, mid_y + 7)]
                pygame.draw.polygon(self.screen, col, pts)
                pygame.draw.polygon(self.screen, (255, 255, 255), pts, 1)
                return
            bx, by = wall_x + pad, mid_y
        else:
            wall_y = y * TILE_SIZE
            mid_x = x * TILE_SIZE + TILE_SIZE // 2
            if kind == "onesided":
                handle = door.get("handle", "a")
                if handle == "a":  # top cell (y-1)
                    tip = (mid_x, wall_y - 3)
                    base_y = wall_y - 14
                    pts = [tip, (mid_x - 7, base_y), (mid_x + 7, base_y)]
                else:  # bottom cell (y)
                    tip = (mid_x, wall_y + 3)
                    base_y = wall_y + 14
                    pts = [tip, (mid_x - 7, base_y), (mid_x + 7, base_y)]
                pygame.draw.polygon(self.screen, col, pts)
                pygame.draw.polygon(self.screen, (255, 255, 255), pts, 1)
                return
            bx, by = mid_x, wall_y + pad

        if kind == "remote":
            pygame.draw.rect(self.screen, (40, 40, 48), (bx - 5, by - 5, 10, 10), border_radius=2)
            pygame.draw.rect(self.screen, (180, 180, 190), (bx - 5, by - 5, 10, 10), 1, border_radius=2)
            pygame.draw.circle(self.screen, (180, 180, 190), (bx, by - 1), 2, 1)
        else:
            # local
            pygame.draw.circle(self.screen, col, (bx, by), 4)
            pygame.draw.circle(self.screen, (255, 255, 255), (bx, by), 4, 1)

    def _draw_lattice(self, rect, orient):
        if rect.width < 3 or rect.height < 3:
            return
        step = 7
        if orient == "v":
            yy = rect.top + step
            while yy < rect.bottom - 1:
                pygame.draw.line(
                    self.screen, SHOJI_LATTICE, (rect.left, yy), (rect.right - 1, yy), 1
                )
                yy += step
        else:
            xx = rect.left + step
            while xx < rect.right - 1:
                pygame.draw.line(
                    self.screen, SHOJI_LATTICE, (xx, rect.top), (xx, rect.bottom - 1), 1
                )
                xx += step

    def _draw_panel(self):
        maze_w = self.width * TILE_SIZE
        win_h = self.screen.get_height()
        panel = pygame.Rect(maze_w + 4, 0, PANEL_WIDTH - 4, max(win_h - HUD_HEIGHT, 100))
        pygame.draw.rect(self.screen, PANEL_BG, panel)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, 1)

        x = panel.x + 10
        y = panel.y + 10

        title = self.font.render("Door dictionary", True, PANEL_TEXT)
        self.screen.blit(title, (x, y))
        y += 28

        # Legend: kinds
        y = self._panel_line(x, y, "TYPES", bold=True)
        y = self._legend_row(x, y, "local", "Local — click when adjacent")
        y = self._legend_row(x, y, "remote", "Remote — chain only (no click)")
        y = self._legend_row(x, y, "onesided", "One-way — stand where the arrow is")
        y += 8

        y = self._panel_line(x, y, "CHAINS (same color flips together)", bold=True)
        y += 2

        for i, comp in enumerate(self.chain_list):
            if y > panel.bottom - 40:
                more = self.font_tiny.render("…", True, PANEL_MUTED)
                self.screen.blit(more, (x, y))
                break
            col = CHAIN_COLORS[i % len(CHAIN_COLORS)]
            pygame.draw.rect(self.screen, col, (x, y + 2, 12, 12), border_radius=2)
            label = self.font_sm.render(
                f"Chain {chr(ord('A') + i)}  ·  {len(comp)} door(s)",
                True,
                PANEL_TEXT,
            )
            self.screen.blit(label, (x + 18, y))
            y += 18
            for edge in comp:
                if y > panel.bottom - 24:
                    break
                d = self.doors[edge]
                st = "open" if d["state"] == 0 else "closed"
                kind = KIND_LABEL.get(d.get("kind", "local"), "?")
                # active now?
                act = can_activate(self.doors, edge, self.player_pos)
                mark = "▶" if act else "·"
                line = self.font_tiny.render(
                    f"  {mark} {kind:7}  {st}",
                    True,
                    col if act else PANEL_MUTED,
                )
                self.screen.blit(line, (x, y))
                y += 15
            y += 6

        y = max(y + 4, panel.bottom - 70)
        y = self._panel_line(x, y, "TIP", bold=True)
        tip = self.font_tiny.render("Glow = usable from where you stand", True, PANEL_MUTED)
        self.screen.blit(tip, (x, y))

    def _panel_line(self, x, y, text, bold=False):
        font = self.font_sm if bold else self.font_tiny
        col = PANEL_TEXT if bold else PANEL_MUTED
        surf = font.render(text, True, col)
        self.screen.blit(surf, (x, y))
        return y + (18 if bold else 15)

    def _legend_row(self, x, y, kind, text):
        # mini badge
        if kind == "remote":
            pygame.draw.rect(self.screen, (40, 40, 48), (x, y, 12, 12), border_radius=2)
            pygame.draw.rect(self.screen, (180, 180, 190), (x, y, 12, 12), 1, border_radius=2)
        elif kind == "onesided":
            pygame.draw.polygon(
                self.screen,
                (70, 145, 230),
                [(x, y + 6), (x + 12, y), (x + 12, y + 12)],
            )
        else:
            pygame.draw.circle(self.screen, (70, 145, 230), (x + 6, y + 6), 5)
        surf = self.font_tiny.render(text, True, PANEL_MUTED)
        self.screen.blit(surf, (x + 18, y))
        return y + 16

    def _draw_hud(self):
        y = self.height * TILE_SIZE + 8
        hud = self.font_sm.render(
            f"Lv {self.current_level}  |  WASD/Arrows  |  Click usable shoji  |  R restart  |  N next",
            True,
            HUD,
        )
        self.screen.blit(hud, (10, y))
        if self.status:
            st = self.font_sm.render(self.status, True, (240, 200, 120))
            self.screen.blit(st, (10, y + 22))
        if self.message:
            msg = self.font_sm.render(self.message, True, (180, 255, 180))
            self.screen.blit(msg, (10, y + 22))
