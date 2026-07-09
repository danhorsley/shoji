#!/usr/bin/env python3
"""
Batch-hunt curate-worthy puzzles offline.

  python hunt_batch.py           # find ~10 keepers
  python hunt_batch.py 20        # find 20 keepers
  python hunt_batch.py 10 200    # 10 keepers, max 200 tries each

Writes to levels/curated/curated_###.json
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from game import Game


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    max_tries = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    pygame.init()
    screen = pygame.display.set_mode((64, 64))
    game = Game(screen)

    saved = 0
    attempt = 0
    # Vary difficulty a bit for variety
    while saved < target and attempt < target * max_tries:
        attempt += 1
        diff = saved % 4
        path = game.hunt_curated(max_tries=max_tries, difficulty=diff)
        if path:
            saved += 1
            print(f"[{saved}/{target}] {path}")
        else:
            print(f"  batch miss (saved {saved}/{target})")

    print(f"Done: {saved} curated after {attempt} hunt calls")
    pygame.quit()


if __name__ == "__main__":
    main()
