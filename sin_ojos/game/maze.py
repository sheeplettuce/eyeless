"""Laberinto en cuadrícula: generación (DFS + 'braiding') y utilidades."""
import random
from collections import deque

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Maze:
    def __init__(self, grid):
        self.grid = grid                      # 1 = pared, 0 = piso
        self.h = len(grid)
        self.w = len(grid[0])
        self.adj = {}                         # tile -> vecinos transitables
        for y in range(self.h):
            for x in range(self.w):
                if grid[y][x] == 0:
                    self.adj[(x, y)] = [(x + dx, y + dy) for dx, dy in DIRS
                                        if grid[y + dy][x + dx] == 0]
        self.floor = list(self.adj.keys())

    def bfs_dist(self, src, limit=None):
        """Distancia en pasos de pasillo desde src (el sonido viaja así)."""
        dist = {src: 0}
        q = deque([src])
        while q:
            cur = q.popleft()
            d = dist[cur]
            if limit is not None and d >= limit:
                continue
            for n in self.adj[cur]:
                if n not in dist:
                    dist[n] = d + 1
                    q.append(n)
        return dist


def generate(cells, braid, rng=None):
    """Backtracker iterativo (DFS) + apertura de callejones para crear ciclos.

    Un laberinto 'perfecto' tiene un único camino entre dos puntos, así que
    DFS, BFS y A* darían la misma ruta. Los ciclos (braid) hacen que la
    elección de algoritmo importe de verdad.
    """
    rng = rng or random.Random()
    w = h = cells * 2 + 1
    grid = [[1] * w for _ in range(h)]
    grid[1][1] = 0
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        opts = []
        for dx, dy in DIRS:
            nx, ny = x + dx * 2, y + dy * 2
            if 0 < nx < w - 1 and 0 < ny < h - 1 and grid[ny][nx] == 1:
                opts.append((dx, dy))
        if opts:
            dx, dy = rng.choice(opts)
            grid[y + dy][x + dx] = 0
            grid[y + dy * 2][x + dx * 2] = 0
            stack.append((x + dx * 2, y + dy * 2))
        else:
            stack.pop()

    for y in range(1, h, 2):
        for x in range(1, w, 2):
            n_open = sum(1 for dx, dy in DIRS if grid[y + dy][x + dx] == 0)
            if n_open == 1 and rng.random() < braid:
                walls = [(dx, dy) for dx, dy in DIRS
                         if grid[y + dy][x + dx] == 1
                         and 0 < x + dx * 2 < w - 1 and 0 < y + dy * 2 < h - 1]
                if walls:
                    dx, dy = rng.choice(walls)
                    grid[y + dy][x + dx] = 0
    return Maze(grid)
