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
| **C** or **★ Curate / Save** | Save current puzzle to `levels/curated/curated_###.json` |
| **G** | **Hunt** — generate until a non-trivial multi-phase puzzle appears, then auto-curate |

Batch hunt (offline):
```bash
python hunt_batch.py 10      # save ~10 keepers
```

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
**Compact chamber puzzles** (Quell-shaped efficiency, shoji rules):
- Small boards (~6×5, grow slowly with level)
- Macro rooms: entry · switch · exit (no heavy maze-fill)
- Exit cut is a **remote**; switch has a **local / one-way** control
- Typical solve: enter switch → flip → short double-back → exit

Generation filters for **decision density**:
- short solutions (move caps)
- low moves-per-toggle
- off-spine switch use + revisits

Edges: `("v", x, y)` vertical · `("h", x, y)` horizontal

Use **C** / Curate to keep gems in `levels/curated/`.
