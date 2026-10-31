"""Los tres algoritmos de búsqueda que mueven al monstruo.

Todos devuelven PathResult con el camino (incluye inicio y meta), el número
de nodos expandidos y el costo. Así se pueden comparar en tools/.
"""
import heapq
import random
from collections import deque
from dataclasses import dataclass, field


@dataclass
class PathResult:
    path: list
    expanded: int
    cost: float
    order: list = field(default_factory=list)   # nodos expandidos, en orden (para el modo dev)
    tree: dict = field(default_factory=dict)    # nodo -> padre (árbol de exploración)


def _rebuild(came, goal):
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = came[cur]
    path.reverse()
    return path


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bfs(maze, start, goal):
    """Búsqueda en anchura: camino más corto en pasos (grafo sin pesos)."""
    came = {start: None}
    q = deque([start])
    expanded = 0
    order = []
    while q:
        cur = q.popleft()
        expanded += 1
        order.append(cur)
        if cur == goal:
            p = _rebuild(came, goal)
            return PathResult(p, expanded, len(p) - 1, order, came)
        for n in maze.adj[cur]:
            if n not in came:
                came[n] = cur
                q.append(n)
    return PathResult([], expanded, float("inf"), order, came)


def dfs(maze, start, goal, rng=None, greedy=True):
    """Búsqueda en profundidad. No garantiza el camino más corto.

    greedy=True ordena los vecinos para probar primero el más cercano a la
    meta (DFS 'sesgado'); greedy=False los mezcla al azar (DFS puro).
    """
    rng = rng or random
    came = {}
    stack = [(start, None)]
    expanded = 0
    order = []
    while stack:
        cur, parent = stack.pop()
        if cur in came:
            continue
        came[cur] = parent
        expanded += 1
        order.append(cur)
        if cur == goal:
            p = _rebuild(came, goal)
            return PathResult(p, expanded, len(p) - 1, order, came)
        nbrs = [n for n in maze.adj[cur] if n not in came]
        rng.shuffle(nbrs)
        if greedy:
            nbrs.sort(key=lambda n: -_manhattan(n, goal))  # el más cercano sale primero
        stack.extend((n, cur) for n in nbrs)
    return PathResult([], expanded, float("inf"), order, came)


def astar(maze, start, goal, cost=None, min_cost=1.0):
    """A* con heurística Manhattan.

    cost(tile) -> costo de ENTRAR a ese tile (>= min_cost). Con cost=None todos
    cuestan 1 y A* es equivalente a BFS pero expandiendo menos nodos. Con costos
    variables es el único de los tres que sabe aprovecharlos.
    """
    g = {start: 0.0}
    came = {start: None}
    heap = [(min_cost * _manhattan(start, goal), 0.0, start)]
    closed = set()
    expanded = 0
    order = []
    while heap:
        _, gc, cur = heapq.heappop(heap)
        if cur in closed:
            continue
        closed.add(cur)
        expanded += 1
        order.append(cur)
        if cur == goal:
            return PathResult(_rebuild(came, goal), expanded, gc, order, came)
        for n in maze.adj[cur]:
            ng = gc + (cost(n) if cost else 1.0)
            if ng < g.get(n, float("inf")):
                g[n] = ng
                came[n] = cur
                heapq.heappush(heap, (ng + min_cost * _manhattan(n, goal), ng, n))
    return PathResult([], expanded, float("inf"), order, came)


def plan(algo, maze, start, goal, rng=None, cost=None, min_cost=1.0):
    if start == goal:
        return PathResult([start], 0, 0.0)
    if algo == "bfs":
        return bfs(maze, start, goal)
    if algo == "dfs":
        return dfs(maze, start, goal, rng, greedy=False)
    if algo == "astar":
        return astar(maze, start, goal, cost, min_cost)
    raise ValueError(f"algoritmo desconocido: {algo}")
