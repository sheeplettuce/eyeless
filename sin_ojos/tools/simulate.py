"""Simula un jugador-bot contra el monstruo (sin ventana) para comparar
algoritmos dentro del juego real.

Uso:  python tools/simulate.py [n_semillas]
El bot camina a la salida evitando (con costo extra) los tiles ruidosos y
se agacha al pisarlos. Se cruza cada dificultad con cada algoritmo.
"""
import dataclasses
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from game.config import DIFFICULTIES
from game.pathfinding import plan
from game.world import World, PLAYING, WON, LOST


class Bot:
    def __init__(self, world):
        self.w = world
        noisy = world.noisy
        cost = lambda t: 1.0 + (4.0 * noisy[t] if t in noisy else 0.0)
        res = plan("astar", world.maze, world.player_tile, world.exit,
                   random.Random(0), cost, 1.0)
        self.path = res.path[1:]

    def step(self, dt):
        w = self.w
        if not self.path:
            return
        tx, ty = self.path[0][0] + 0.5, self.path[0][1] + 0.5
        dx, dy = tx - w.px, ty - w.py
        if math.hypot(dx, dy) < 0.12:
            self.path.pop(0)
            return
        w.move_player(dx, dy, self.path[0] in w.noisy, dt)


def run(diff, seed, dt=0.05, limit=300.0):
    w = World(diff, seed)
    bot = Bot(w)
    while w.state == PLAYING and w.time < limit:
        bot.step(dt)
        w.update(dt)
    return w


def hunt(diff, seed, dt=0.05, limit=90.0):
    """Jugador quieto que hace ruido cada 6 s a ~6 pasos del monstruo.
    Aísla la calidad de la persecución: tiempo hasta ser atrapado."""
    w = World(diff, seed)
    w.monster.deaf_until = 0.0
    dm = w.maze.bfs_dist(w.monster.here)
    cands = [t for t, d in dm.items() if d == min(6, diff.hear_radius - 1)]
    tile = random.Random(seed).choice(cands)
    w.px, w.py, w.player_tile = tile[0] + 0.5, tile[1] + 0.5, tile
    next_noise = 0.0
    while w.state == PLAYING and w.time < limit:
        if w.time >= next_noise:
            w.emit_noise(tile, diff.hear_radius, "paso")
            next_noise += 6.0
        w.update(dt)
    return w


def main_hunt(n=60):
    print("\nESCENARIO CACERÍA: jugador quieto, hace ruido cada 6 s (límite 90 s)")
    print(f"{'dificultad':10s} {'algoritmo':8s} {'atrapado%':>10s} {'t hasta captura':>16s} {'nodos/plan':>11s}")
    for base in DIFFICULTIES:
        for algo in ("dfs", "bfs", "astar"):
            diff = dataclasses.replace(base, algorithm=algo)
            lost, times, exp, plans = 0, [], 0, 0
            for seed in range(n):
                w = hunt(diff, seed)
                lost += w.state == LOST
                times.append(w.time)
                exp += w.monster.total_expanded
                plans += max(1, w.monster.replans)
            mark = " <- por defecto" if algo == base.algorithm else ""
            print(f"{base.label:10s} {algo:8s} {100*lost/n:10.0f} {sum(times)/n:16.1f} {exp/plans:11.1f}{mark}")
        print()


def main(n=40):
    print(f"{'dificultad':10s} {'algoritmo':8s} {'ganó%':>6s} {'atrapado%':>10s} "
          f"{'t medio':>8s} {'oyó/paso':>9s} {'nodos/plan':>11s}")
    for base in DIFFICULTIES:
        for algo in ("dfs", "bfs", "astar"):
            diff = dataclasses.replace(base, algorithm=algo)
            won = lost = 0
            times, heard, exp, plans = [], 0, 0, 0
            for seed in range(n):
                w = run(diff, seed)
                won += w.state == WON
                lost += w.state == LOST
                times.append(w.time)
                heard += w.monster.heard_count
                exp += w.monster.total_expanded
                plans += max(1, w.monster.replans)
            mark = " <- por defecto" if algo == base.algorithm else ""
            print(f"{base.label:10s} {algo:8s} {100*won/n:6.0f} {100*lost/n:10.0f} "
                  f"{sum(times)/n:8.1f} {heard/n:9.1f} {exp/plans:11.1f}{mark}")
        print()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    main(n)
    main_hunt(n)
