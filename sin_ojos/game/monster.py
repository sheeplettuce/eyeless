"""El monstruo: ciego, solo oye. Mantiene una *creencia* (mapa de
probabilidad) de dónde estás y usa un algoritmo de búsqueda para llegar.

Estados:
  PATRULLA  -> camina entre puntos al azar, despacio.
  INVESTIGA -> oyó algo: va al lugar donde cree que sonó.
  BUSCA     -> llegó y no hay nadie: barre las zonas de mayor probabilidad
               mientras la creencia se difunde (pudiste moverte).
"""
import math
import random

from .config import DIFFUSE_PERIOD, PLAYER_REVEAL_TIME
from .pathfinding import plan

PATROL, INVESTIGATE, SEARCH = "PATRULLA", "INVESTIGA", "BUSCA"


class Monster:
    def __init__(self, maze, diff, start, rng=None):
        self.maze = maze
        self.diff = diff
        self.rng = rng or random.Random()
        self.cur = start          # tile del que sale
        self.nxt = start          # tile al que va
        self.t = 0.0              # progreso 0..1 entre cur y nxt
        self.path = []            # tiles que faltan después de nxt
        self.goal = None
        self.perceived = None     # último punto donde "creyó" oír el ruido
        self.focus_target = None
        self.focus_until = 0.0
        self.track_player = False
        self._now = 0.0
        self.state = PATROL
        self.search_left = 0.0
        self.idle = 1.0
        self.deaf_until = 0.0
        self.incapacitated_until = 0.0
        self._diffuse_t = 0.0
        self.belief = []
        self._uniform()
        # métricas
        self.last_expanded = 0
        self.total_expanded = 0
        self.replans = 0
        self.last_path_len = 0
        self.heard_count = 0
        self.last_plan = None     # traza del último plan (la usa el modo dev)

    # ------------------------------------------------------------ posición
    @property
    def pos(self):
        return (self.cur[0] + (self.nxt[0] - self.cur[0]) * self.t + 0.5,
                self.cur[1] + (self.nxt[1] - self.cur[1]) * self.t + 0.5)

    @property
    def here(self):
        return self.nxt if self.t > 0 else self.cur

    def debug_path(self):
        return [self.here] + list(self.path)

    # ------------------------------------------------------------ creencia
    def _idx(self, t):
        return t[1] * self.maze.w + t[0]

    def _uniform(self):
        w, h = self.maze.w, self.maze.h
        self.belief = [0.0] * (w * h)
        p = 1.0 / len(self.maze.floor)
        for t in self.maze.floor:
            self.belief[self._idx(t)] = p

    def _set_belief(self, center):
        sigma = self.diff.belief_sigma
        dm = self.maze.bfs_dist(center, limit=int(3 * sigma) + 1)
        b = [0.0] * len(self.belief)
        for t, d in dm.items():
            b[self._idx(t)] = math.exp(-d * d / (2 * sigma * sigma))
        s = sum(b)
        floor = 0.03                       # nunca descarta nada del todo
        u = 1.0 / len(self.maze.floor)
        for t in self.maze.floor:
            i = self._idx(t)
            b[i] = (1 - floor) * b[i] / s + floor * u
        self.belief = b

    def _diffuse(self, rate):
        b = self.belief
        new = [0.0] * len(b)
        w = self.maze.w
        for t, ns in self.maze.adj.items():
            i = t[1] * w + t[0]
            m = b[i]
            new[i] += m * (1 - rate)
            share = m * rate / len(ns)
            for n in ns:
                new[n[1] * w + n[0]] += share
        self.belief = new

    def _clear(self, tile):
        self.belief[self._idx(tile)] = 0.0
        s = sum(self.belief)
        if s < 1e-9:
            self._uniform()
        else:
            inv = 1.0 / s
            self.belief = [v * inv for v in self.belief]

    # ------------------------------------------------------------ oído
    def hear(self, tile, radius, now, exact_target=None):
        """Un ruido en `tile`. Devuelve True si el monstruo lo oyó.

        El sonido viaja por los pasillos (distancia BFS), no en línea recta:
        un ruido detrás de una pared puede estar lejísimos en pasos.
        """
        if now < self.deaf_until:
            return False
        dist_map = self.maze.bfs_dist(tile, limit=radius)
        d = dist_map.get(self.here)
        if d is None:
            return False
        self.perceived = exact_target if exact_target is not None else tile
        self.focus_target = self.perceived
        self.track_player = exact_target is not None
        self.focus_until = now + PLAYER_REVEAL_TIME
        self._set_belief(self.perceived)
        self.state = INVESTIGATE
        self.search_left = self.diff.search_time
        self.idle = 0.0
        self.heard_count += 1
        self._plan(self.perceived)
        return True

    # ------------------------------------------------------------ planificación
    def _plan(self, goal):
        start = self.here
        cost, min_cost = None, 1.0
        if self.diff.algorithm == "astar":
            bel, w = self.belief, self.maze.w
            mx = max(bel) or 1.0
            cost = lambda n: 1.0 - 0.5 * bel[n[1] * w + n[0]] / mx
            min_cost = 0.5
        res = plan(self.diff.algorithm, self.maze, start, goal, self.rng, cost, min_cost)
        self.last_expanded = res.expanded
        self.total_expanded += res.expanded
        self.replans += 1
        self.goal = goal
        p = res.path or [start]
        self.last_path_len = len(p) - 1
        self.last_plan = {"id": self.replans, "algo": self.diff.algorithm, "start": start,
                          "goal": goal, "order": res.order, "tree": res.tree,
                          "path": list(p), "cost": res.cost, "state": self.state}
        if self.t > 0 and len(p) > 1 and p[1] == self.cur:
            # le conviene dar media vuelta en mitad del pasillo
            self.cur, self.nxt = self.nxt, self.cur
            self.t = 1.0 - self.t
            self.path = p[2:]
        else:
            self.path = p[1:]

    def _new_patrol(self):
        for _ in range(8):
            g = self.rng.choice(self.maze.floor)
            if abs(g[0] - self.here[0]) + abs(g[1] - self.here[1]) >= 5:
                break
        self._plan(g)

    def _next_search_target(self):
        dist = self.maze.bfs_dist(self.here)
        best, best_s = None, -1.0
        for t, d in dist.items():
            if d == 0:
                continue
            s = self.belief[self._idx(t)] / (1.0 + 0.12 * d)
            if s > best_s:
                best, best_s = t, s
        if best is None:
            best = self.rng.choice(self.maze.floor)
        self._plan(best)

    def _speed(self):
        v = self.diff.monster_speed
        if self.state == PATROL:
            return v * self.diff.patrol_factor
        if self.state == SEARCH:
            return v * 0.85
        return v

    def current_speed(self):
        """Velocidad real en tiles/s (0 si está quieto escuchando o sordo)."""
        if self._now < self.incapacitated_until:
            return 0.0
        if self.idle > 0 or (self.cur == self.nxt and not self.path):
            return 0.0
        return self._speed()

    def incapacitate(self, now, duration):
        self.incapacitated_until = max(self.incapacitated_until, now + duration)

    # ------------------------------------------------------------ bucle
    def _on_arrive(self):
        if self.state == SEARCH:
            self._clear(self.cur)

    def _on_path_done(self):
        if self.state == INVESTIGATE:
            if self._now < self.focus_until:
                self.idle = 0.08
                return
            self.state = SEARCH
            self.idle = 0.8                      # se queda escuchando un instante
            self._clear(self.here)
            self._next_search_target()
        elif self.state == SEARCH:
            if self.search_left <= 0:
                self.state = PATROL
                self._new_patrol()
            else:
                self._next_search_target()
        else:
            self.idle = self.rng.uniform(0.5, 1.5)
            self._new_patrol()

    def update(self, dt, now, player_tile=None):
        self._now = now
        if now < self.incapacitated_until:
            return
        self._diffuse_t += dt
        if self._diffuse_t >= DIFFUSE_PERIOD:
            self._diffuse_t = 0.0
            self._diffuse(self.diff.diffusion)
        if self.focus_target is not None and now >= self.focus_until:
            self.focus_target = None
            self.track_player = False
            if self.state == INVESTIGATE:
                self.state = SEARCH
                self.idle = 0.0
                self._next_search_target()
        elif self.focus_target is not None and self.track_player and self.state == INVESTIGATE:
            if player_tile is not None and player_tile != self.focus_target:
                self.focus_target = player_tile
                self.perceived = player_tile
                self._set_belief(player_tile)
                self.idle = 0.0
                self._plan(player_tile)
        if now < self.deaf_until:
            return
        if self.state == SEARCH:
            self.search_left -= dt
        if self.idle > 0:
            self.idle -= dt
            return
        if self.cur == self.nxt and not self.path:
            self._on_path_done()
            if self.idle > 0 or (self.cur == self.nxt and not self.path):
                return
        if self.cur == self.nxt and self.path:
            self.nxt = self.path.pop(0)
            self.t = 0.0
        self.t += self._speed() * dt
        while self.t >= 1.0:
            self.cur = self.nxt
            self.t -= 1.0
            self._on_arrive()
            if self.path:
                self.nxt = self.path.pop(0)
            else:
                self.t = 0.0
                self._on_path_done()
                if self.idle > 0 or not self.path:
                    break
                self.nxt = self.path.pop(0)
