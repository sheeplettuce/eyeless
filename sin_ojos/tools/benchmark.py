"""Compara DFS / BFS / A* sobre laberintos con ciclos, sin jugar.

Uso:  python tools/benchmark.py [n_laberintos]
Mide largo del camino (vs. el óptimo), nodos expandidos y tiempo.
"""
import os
import random
import statistics as st
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from game.config import DIFFICULTIES
from game.maze import generate
from game.pathfinding import bfs, dfs, astar


def main(n=150):
    rng = random.Random(1)
    algos = {
        "DFS puro (vecinos al azar)": lambda m, a, b: dfs(m, a, b, rng, greedy=False),
        "DFS sesgado a la meta": lambda m, a, b: dfs(m, a, b, rng, greedy=True),
        "BFS": lambda m, a, b: bfs(m, a, b),
        "A* (costo uniforme)": lambda m, a, b: astar(m, a, b),
    }
    for diff in DIFFICULTIES:
        print(f"\n=== Laberinto {diff.cells}x{diff.cells} (braid={diff.braid}) ===")
        stats = {k: {"len": [], "exp": [], "us": []} for k in algos}
        for _ in range(n):
            m = generate(diff.cells, diff.braid, rng)
            for _ in range(5):
                a, b = rng.sample(m.floor, 2)
                opt = bfs(m, a, b).cost
                for name, fn in algos.items():
                    t0 = time.perf_counter()
                    r = fn(m, a, b)
                    dt = (time.perf_counter() - t0) * 1e6
                    stats[name]["len"].append(r.cost / opt)
                    stats[name]["exp"].append(r.expanded)
                    stats[name]["us"].append(dt)
        print(f"{'algoritmo':30s} {'largo/óptimo':>13s} {'nodos':>8s} {'µs':>8s}")
        for name, s in stats.items():
            print(f"{name:30s} {st.mean(s['len']):13.2f} {st.mean(s['exp']):8.1f} {st.mean(s['us']):8.0f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
