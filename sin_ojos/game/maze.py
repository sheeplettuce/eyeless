"""Laberinto en cuadrícula: generación (DFS + 'braiding') y utilidades."""
import random
from collections import deque

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Maze:
    def __init__(self, grid, doors=None, room_tiles=None):
        self.grid = grid                      # 1 = pared, 0 = piso
        self.h = len(grid)
        self.w = len(grid[0])
        self.start = (1, 1)
        self.doors = {tile: False for tile in (doors or ())}
        self.room_tiles = set(room_tiles or ())
        self.rooms = []
        unvisited = set(self.room_tiles)
        while unvisited:
            room = {unvisited.pop()}
            pending = list(room)
            while pending:
                x, y = pending.pop()
                for dx, dy in DIRS:
                    neighbor = (x + dx, y + dy)
                    if neighbor in unvisited:
                        unvisited.remove(neighbor)
                        room.add(neighbor)
                        pending.append(neighbor)
            self.rooms.append(room)
        self._rebuild_graph()

    def _rebuild_graph(self):
        for (x, y), opened in self.doors.items():
            self.grid[y][x] = 0 if opened else 1
        self.adj = {}                         # tile -> vecinos transitables
        for y in range(self.h):
            for x in range(self.w):
                if self.grid[y][x] == 0:
                    self.adj[(x, y)] = [(x + dx, y + dy) for dx, dy in DIRS
                                        if self.grid[y + dy][x + dx] == 0]
        self.floor = list(self.bfs_dist(self.start))

    def set_door(self, tile, opened):
        if tile not in self.doors:
            raise ValueError(f"no hay puerta en {tile}")
        self.doors[tile] = opened
        self._rebuild_graph()

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
    cells += 12
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

    wide_segments = []
    for y in range(2, h - 2):
        for x in range(2, w - 2):
            if grid[y][x] == 0 and grid[y][x + 1] == 0:
                for side in (-1, 1):
                    strip = ((x, y + side), (x + 1, y + side))
                    if all(grid[sy][sx] == 1 for sx, sy in strip):
                        wide_segments.append(strip)
            if grid[y][x] == 0 and grid[y + 1][x] == 0:
                for side in (-1, 1):
                    strip = ((x + side, y), (x + side, y + 1))
                    if all(grid[sy][sx] == 1 for sx, sy in strip):
                        wide_segments.append(strip)
    rng.shuffle(wide_segments)
    widened = set()
    for strip in wide_segments:
        if any(tile in widened for tile in strip):
            continue
        for sx, sy in strip:
            grid[sy][sx] = 0
            widened.add((sx, sy))
        if len(widened) >= max(6, cells // 5 * 2):
            break

    doors, room_tiles = [], set()
    occupied = []

    def reachable(source_grid):
        seen = {(1, 1)}
        queue = deque(seen)
        while queue:
            x, y = queue.popleft()
            for dx, dy in DIRS:
                neighbor = (x + dx, y + dy)
                if source_grid[neighbor[1]][neighbor[0]] == 0 and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen

    for preferred_size in (5, 7, 9, 5, 7):
        old_reachable = reachable(grid)
        selected = None
        sizes = (preferred_size, *(size for size in (5, 7, 9, 11)
                                   if size != preferred_size))
        for size in sizes:
            half = size // 2
            positions = [(x, y) for y in range(2, h - size - 1)
                         for x in range(2, w - size - 1)]
            rng.shuffle(positions)
            for x, y in positions:
                bounds = (x - 1, y - 1, x + size, y + size)
                if any(not (bounds[2] < other[0] or bounds[0] > other[2]
                            or bounds[3] < other[1] or bounds[1] > other[3])
                       for other in occupied):
                    continue
                entries = (
                    ((x + half, y), (x + half, y - 1)),
                    ((x + half, y + size - 1), (x + half, y + size)),
                    ((x, y + half), (x - 1, y + half)),
                    ((x + size - 1, y + half), (x + size, y + half)),
                )
                for door, corridor in entries:
                    if grid[corridor[1]][corridor[0]] != 0:
                        continue
                    trial = [row[:] for row in grid]
                    for ry in range(y, y + size):
                        for rx in range(x, x + size):
                            trial[ry][rx] = 1
                    for ry in range(y + 1, y + size - 1):
                        for rx in range(x + 1, x + size - 1):
                            trial[ry][rx] = 0
                    trial[door[1]][door[0]] = 0
                    footprint = {(rx, ry) for ry in range(y, y + size)
                                 for rx in range(x, x + size)}
                    if old_reachable - footprint <= reachable(trial):
                        selected = size, x, y, door, bounds
                        break
                if selected:
                    break
            if selected:
                break
        if not selected:
            break
        size, x, y, door, bounds = selected
        for ry in range(y, y + size):
            for rx in range(x, x + size):
                grid[ry][rx] = 1
        for ry in range(y + 1, y + size - 1):
            for rx in range(x + 1, x + size - 1):
                grid[ry][rx] = 0
                room_tiles.add((rx, ry))
        grid[door[1]][door[0]] = 1
        doors.append(door)
        occupied.append(bounds)

    return Maze(grid, doors, room_tiles)
