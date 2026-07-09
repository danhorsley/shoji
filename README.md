# Shoji - Entangled Doors Puzzle

Top-down puzzle: explore a Japanese-house maze of rooms where shoji doors
are entangled in color-coded chains.

## How to Run
```bash
pip install pygame
python main.py
```

### Controls
| Input | Action |
|-------|--------|
| **Arrow keys / WASD** | Move |
| **Click** a usable shoji | Flip its whole chain |
| **R** | Restart level |
| **N** | Next level |

Usable doors **glow** in their chain color when you stand where you can operate them.

### Door types
| Type | Badge | How it moves |
|------|-------|----------------|
| **Local** | Filled circle | Click when standing on either side |
| **Remote** | Lock square | Never clickable — only flips via chain |
| **One-way** | Arrow | Click only from the arrow (handle) side |

### Entanglement
- Same **frame color** = same chain (see the side dictionary)
- Clicking any *usable* door in a chain flips **every** door in that chain
- Each door keeps its own open/closed polarity (mixed starts are common)

### Visuals
- Brown **lines** = permanent walls
- Tan tiles = floor
- Colored shoji frames = chain membership
- Red circle = player · Green square = exit
- Right panel = **door dictionary** (types + live chain status)

### Level model
Edge-based geometry with a **switch-room template**:
- Entry room + side **switch** room + **exit wing**
- Exit cut is often a **remote** door
- Switch holds a **local / one-way** control on the same chain (mixed polarity)
- Typical solve: enter switch → flip chain → **double back** → exit wing

Generation searches for multi-phase solutions (toggles, revisits, off-spine
switch use) — not just “solvable.”

Edges: `("v", x, y)` vertical · `("h", x, y)` horizontal
