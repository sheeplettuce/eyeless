"""Modo dev (casilla / F1): lo que 'piensa' y 'es' el monstruo, en vivo.

Izquierda: mapa con el monstruo, el jugador, su creencia y la búsqueda de caminos animada
como un árbol de nodos (cada replanificación se vuelve a reproducir paso a paso).
Derecha: especificaciones del monstruo y datos del algoritmo.
"""
import math

import pygame

from .config import SCREEN_W, SCREEN_H, SPRINT_MAX, WALK_SPEED, STEP_STRIDE, FOG_RANGE
from .monster import PATROL, INVESTIGATE, SEARCH

ALGO_INFO = {
    "dfs": ("DFS · en profundidad", "pila (LIFO)", "no óptimo, da rodeos"),
    "bfs": ("BFS · en anchura", "cola (FIFO)", "óptimo en pasos"),
    "astar": ("A* · Manhattan", "cola prioridad f=g+h", "óptimo, pesa creencia"),
}
STATE_COL = {PATROL: (120, 200, 255), INVESTIGATE: (255, 205, 70), SEARCH: (255, 110, 80)}
C_WALL, C_FLOOR = (55, 55, 62), (18, 18, 22)
C_TEXT, C_DIM = (232, 232, 238), (150, 150, 162)
C_PATH, C_FRONT = (255, 224, 70), (255, 150, 40)
C_MON, C_GOAL, C_PEAK = (255, 45, 45), (255, 70, 220), (200, 120, 255)


def _lerp(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


class DevView:
    def __init__(self):
        self._plan_id = None        # qué plan se está reproduciendo
        self._t0 = 0                # ms (reloj real) en que empezó la reproducción
        self._frontier = []
        self._cell = None
        self._map_key = None
        self._map_background = None
        self._belief_source = None
        self._belief_overlay = None

    # ------------------------------------------------------------------ utilidades
    def _plan_progress(self, plan):
        """Cuántos nodos de la búsqueda ya se 'ven' (reproducción animada del algoritmo)."""
        if plan is None:
            return 0, 0
        now = pygame.time.get_ticks()
        if plan["id"] != self._plan_id:
            self._plan_id, self._t0 = plan["id"], now
            order = set(plan["order"])
            self._frontier = [n for n in plan["tree"] if n not in order]   # descubiertos, sin expandir
        n = len(plan["order"])
        rate = max(45.0, n / 1.6)                 # nodos/s: ~1.6 s para reproducir cualquier búsqueda
        return min(n, int((now - self._t0) / 1000.0 * rate) + 1), n

    # ------------------------------------------------------------------ dibujo
    def draw(self, screen, world, font, small):
        m, mon = world.maze, world.monster
        map_size = 220
        ts = max(4, min(8, (map_size - 8) // m.w))
        ox, oy = SCREEN_W - map_size - 16, 20
        map_key = (id(m), map_size, ts, tuple(sorted(m.doors.items())))
        if map_key != self._map_key:
            self._map_background = pygame.Surface((map_size, map_size + 38),
                                                  pygame.SRCALPHA)
            self._map_background.fill((4, 4, 8, 225))
            for y in range(m.h):
                for x in range(m.w):
                    rect = pygame.Rect(6 + x * ts, 30 + y * ts, ts, ts)
                    if m.grid[y][x]:
                        pygame.draw.rect(self._map_background, C_WALL, rect)
                    else:
                        shade = world.floor_darkness.get((x, y), 0.0)
                        if (x, y) in world.noisy:
                            shade = min(0.55, shade + 0.055)
                        base = tuple(int(c * (1 - shade)) for c in C_FLOOR)
                        pygame.draw.rect(self._map_background, base, rect)
            self._map_key = map_key
            self._belief_source = None

        if mon.belief is not self._belief_source:
            self._belief_overlay = pygame.Surface((map_size, map_size + 38),
                                                  pygame.SRCALPHA)
            self._belief_overlay.fill((0, 0, 0, 0))
            for y in range(m.h):
                for x in range(m.w):
                    if m.grid[y][x]:
                        continue
                    belief = mon.belief[y * m.w + x]
                    if belief * len(m.floor) > 0.03:
                        red = min(160, int(belief * len(m.floor) * 55))
                        pygame.draw.rect(self._belief_overlay, (red, 0, 0),
                                         (6 + x * ts, 30 + y * ts, ts, ts))
            self._belief_source = mon.belief

        screen.blit(self._map_background, (ox - 6, oy - 8))
        screen.blit(self._belief_overlay, (ox - 6, oy - 8))
        screen.blit(font.render("MAPA DEV", True, (255, 100, 100)), (ox, oy - 4))

        def cen(tile):
            return (ox + (tile[0] + 0.5) * ts, oy + 22 + (tile[1] + 0.5) * ts)

        map_y = oy + 22
        plan = mon.last_plan
        shown, total = self._plan_progress(plan)
        if plan:
            order, tree = plan["order"], plan["tree"]
            visible = set(order[:shown])
            for node in order[:shown]:
                parent = tree.get(node)
                if parent in visible:
                    pygame.draw.line(screen, (40, 120, 230), cen(parent), cen(node), 1)
            if shown < total and shown:
                pygame.draw.circle(screen, (230, 230, 230), cen(order[shown - 1]), 3)
            if len(plan["path"]) > 1:
                pygame.draw.lines(screen, C_PATH, False, [cen(t) for t in plan["path"]], 2)
            pygame.draw.circle(screen, C_GOAL, cen(plan["goal"]), 4, 1)

        ex, ey = world.exit
        pygame.draw.rect(screen, (80, 230, 120), (ox + ex * ts + 1, map_y + ey * ts + 1, ts - 2, ts - 2))
        for point in world.blue_points:
            pygame.draw.circle(screen, (70, 160, 255), cen(point), 2)
        mx, my = mon.pos
        pygame.draw.circle(screen, C_MON, (int(ox + mx * ts), int(map_y + my * ts)), max(3, ts // 2))
        pygame.draw.circle(screen, (255, 255, 255),
                           (int(ox + world.px * ts), int(map_y + world.py * ts)), max(2, ts // 3))

        bottom_y = SCREEN_H - 126
        panel = pygame.Surface((SCREEN_W, 126), pygame.SRCALPHA)
        panel.fill((4, 4, 8, 232))
        screen.blit(panel, (0, bottom_y))
        pygame.draw.line(screen, (120, 45, 50), (0, bottom_y), (SCREEN_W, bottom_y), 1)
        focus = max(0.0, mon.focus_until - world.time)
        stamina = world.stamina / SPRINT_MAX * 100
        rows = [
            (f"MODO DEV | {mon.state} | Monstruo {mon.here}",
             f"Jugador {world.player_tile} | Rastreo exacto {focus:.1f}s"),
            (f"IA {world.diff.algorithm.upper()} | Meta {mon.goal} | {mon.current_speed():.1f} tiles/s",
             f"Búsqueda {shown}/{total} | Oídos {mon.heard_count} | Pasillo {world.mon_dist}"),
            (f"Resistencia {stamina:.0f}% | Puntos azules {len(world.blue_points)}",
             f"Nodos {mon.last_expanded} último / {mon.total_expanded} total"),
        ]
        for row, (left, right) in enumerate(rows):
            screen.blit(small.render(left, True, (225, 225, 232)), (16, bottom_y + 12 + row * 24))
            screen.blit(small.render(right, True, (190, 195, 205)), (500, bottom_y + 12 + row * 24))
        pygame.draw.rect(screen, (38, 38, 48), (16, bottom_y + 91, SCREEN_W - 32, 5))
        if total:
            pygame.draw.rect(screen, (70, 210, 230),
                             (16, bottom_y + 91, int((SCREEN_W - 32) * shown / total), 5))
        stamina_bar = pygame.Rect(16, bottom_y + 105, 150, 9)
        pygame.draw.rect(screen, (35, 35, 44), stamina_bar)
        stamina_bar.width = int(stamina_bar.width * world.stamina / SPRINT_MAX)
        pygame.draw.rect(screen, (70, 165, 255), stamina_bar)

    def _draw_legacy(self, screen, world, font, small):
        m, mon = world.maze, world.monster
        ts = max(6, min(18, (SCREEN_H - 170) // m.h, 340 // m.w))
        ox, oy = 10, 34
        mw, mh = ts * m.w, ts * m.h
        if self._cell is None or self._cell.get_width() != ts:
            self._cell = pygame.Surface((ts, ts), pygame.SRCALPHA)

        screen.fill((7, 7, 10))
        rx = ox + mw + 18
        pygame.draw.line(screen, (45, 45, 54), (rx - 10, 8), (rx - 10, SCREEN_H - 8), 1)
        screen.blit(font.render("MODO DEV", True, (255, 90, 90)), (ox, 8))
        screen.blit(small.render("F1 o casilla para ocultar", True, C_DIM), (ox + 130, 13))

        def cen(t):
            return (ox + (t[0] + 0.5) * ts, oy + (t[1] + 0.5) * ts)

        # ---- mapa base: paredes, creencia, tiles ruidosos
        mx_b = max(mon.belief) or 1.0
        informative = mx_b * len(m.floor) > 1.8
        for y in range(m.h):
            for x in range(m.w):
                r = pygame.Rect(ox + x * ts, oy + y * ts, ts, ts)
                if m.grid[y][x]:
                    pygame.draw.rect(screen, C_WALL, r)
                    continue
                shade = world.floor_darkness.get((x, y), 0.0)
                if (x, y) in world.noisy:
                    shade = min(0.55, shade + 0.055)
                floor = tuple(int(c * (1 - shade)) for c in C_FLOOR)
                pygame.draw.rect(screen, floor, r)
                v = mon.belief[y * m.w + x] / mx_b
                if informative and v > 0.02:
                    self._cell.fill((255, 50, 50, int(35 + 150 * v)))
                    screen.blit(self._cell, r)
        ex, ey = world.exit
        pygame.draw.rect(screen, (80, 230, 120), (ox + ex * ts + 2, oy + ey * ts + 2, ts - 4, ts - 4))

        # ---- proceso de búsqueda como árbol de nodos
        plan = mon.last_plan
        shown, total = self._plan_progress(plan)
        done = plan is not None and shown >= total
        if plan:
            order, tree = plan["order"], plan["tree"]
            seen = set(order[:shown])
            r_node = max(2, ts // 4)
            for i, node in enumerate(order[:shown]):
                par = tree.get(node)
                if par is not None and par in seen:
                    col = _lerp((50, 80, 255), (70, 255, 225), i / max(1, total - 1))
                    pygame.draw.line(screen, col, cen(par), cen(node), max(1, ts // 8))
            for i, node in enumerate(order[:shown]):
                col = _lerp((50, 80, 255), (70, 255, 225), i / max(1, total - 1))
                pygame.draw.circle(screen, col, cen(node), r_node)
            if done:
                for node in self._frontier:
                    pygame.draw.circle(screen, C_FRONT, cen(node), r_node, 1)
            elif shown:
                pygame.draw.circle(screen, (255, 255, 255), cen(order[shown - 1]), r_node + 3, 2)
            pygame.draw.circle(screen, (90, 255, 140), cen(plan["start"]), r_node + 3, 2)     # origen
            gx, gy = cen(plan["goal"])
            d = ts // 2
            pygame.draw.line(screen, C_GOAL, (gx - d, gy - d), (gx + d, gy + d), 2)             # meta (X)
            pygame.draw.line(screen, C_GOAL, (gx - d, gy + d), (gx + d, gy - d), 2)

        # ---- camino que le queda al monstruo (cuando la búsqueda ya terminó de reproducirse)
        pts = [cen(t) for t in mon.debug_path()]
        if done and len(pts) > 1:
            pygame.draw.lines(screen, C_PATH, False, pts, max(2, ts // 6))

        # ---- ruidos recientes, creencia, monstruo, jugador
        if mon.perceived:
            pygame.draw.circle(screen, (90, 170, 255), cen(mon.perceived), ts // 2, 2)
        for ev in world.noise_log:
            age = world.time - ev.time
            if age < 3.0:
                c = (90, 170, 255) if ev.heard else (120, 120, 120)
                pygame.draw.circle(screen, c, cen(ev.tile), int(ts * (0.5 + age * 1.5)), 1)
        peak = max(range(len(mon.belief)), key=mon.belief.__getitem__)
        pk = (peak % m.w, peak // m.w)
        if informative:
            px_, py_ = cen(pk)
            d = ts // 2
            pygame.draw.polygon(screen, C_PEAK, [(px_, py_ - d), (px_ + d, py_), (px_, py_ + d), (px_ - d, py_)], 2)
        mpx, mpy = mon.pos
        mc = (ox + mpx * ts, oy + mpy * ts)
        pygame.draw.circle(screen, C_MON, mc, ts // 2 + 2)
        pygame.draw.circle(screen, (255, 255, 255), mc, ts // 2 + 2, 1)
        lab = small.render("M", True, (255, 255, 255))
        screen.blit(lab, lab.get_rect(center=mc))
        pc = (ox + world.px * ts, oy + world.py * ts)
        pygame.draw.circle(screen, (255, 255, 255), pc, ts // 3 + 1)
        pygame.draw.line(screen, (255, 255, 255), pc,
                         (pc[0] + math.cos(world.angle) * ts * 0.9, pc[1] + math.sin(world.angle) * ts * 0.9), 2)

        # ---- barra de progreso y leyenda bajo el mapa
        by = oy + mh + 6
        screen.blit(small.render(f"Búsqueda: {shown}/{total} nodos expandidos"
                                 + ("" if not plan else f"   ({ALGO_INFO[plan['algo']][1].split()[0]})"),
                                 True, C_TEXT), (ox, by))
        pygame.draw.rect(screen, (40, 40, 48), (ox, by + 18, mw, 5))
        if total:
            pygame.draw.rect(screen, (70, 255, 225), (ox, by + 18, int(mw * shown / total), 5))
        legend = [("dot", C_MON, "Monstruo"), ("dot", (255, 255, 255), "Jugador"), ("x", C_GOAL, "Meta"),
                  ("dot", (60, 150, 255), "Nodo expandido"), ("ring", C_FRONT, "Frontera"),
                  ("line", C_PATH, "Camino"), ("dia", C_PEAK, "Pico creencia"), ("sq", (230, 70, 70), "Creencia")]
        lx, ly = ox, by + 30
        for kind, col, txt in legend:
            tw = small.size(txt)[0] + 20
            if lx + tw > ox + mw:
                lx, ly = ox, ly + 17
            c = (lx + 6, ly + 7)
            if kind == "dot":
                pygame.draw.circle(screen, col, c, 5)
            elif kind == "ring":
                pygame.draw.circle(screen, col, c, 5, 1)
            elif kind == "line":
                pygame.draw.line(screen, col, (lx, c[1]), (lx + 12, c[1]), 3)
            elif kind == "x":
                pygame.draw.line(screen, col, (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), 2)
                pygame.draw.line(screen, col, (c[0] - 4, c[1] + 4), (c[0] + 4, c[1] - 4), 2)
            elif kind == "dia":
                pygame.draw.polygon(screen, col, [(c[0], c[1] - 5), (c[0] + 5, c[1]), (c[0], c[1] + 5), (c[0] - 5, c[1])], 2)
            else:
                pygame.draw.rect(screen, col, (c[0] - 4, c[1] - 4, 9, 9))
            screen.blit(small.render(txt, True, C_DIM), (lx + 16, ly))
            lx += tw + 10

        # ---- panel de especificaciones (dos columnas)
        d_ = world.diff
        mt = mon.here
        dist_line = math.hypot(mpx - world.px, mpy - world.py)
        corr = world.mon_dist
        info = ALGO_INFO[d_.algorithm]
        spd = mon.current_speed()
        goal_txt = f"({mon.goal[0]}, {mon.goal[1]})" if mon.goal else "—"
        col_a = [
            ("MONSTRUO", None, None),
            ("Estado", mon.state, STATE_COL.get(mon.state, C_TEXT)),
            ("Tile", f"({mt[0]}, {mt[1]})", None),
            ("Posición", f"({mpx:.2f}, {mpy:.2f})", None),
            ("Meta", goal_txt, C_GOAL),
            ("Vel. ahora", f"{spd:.1f} tiles/s", None),
            ("Vel. base", f"{d_.monster_speed:.1f}  (jug. {WALK_SPEED:.1f})", None),
            ("Patr. / busca", f"{d_.monster_speed * d_.patrol_factor:.1f} / {d_.monster_speed * 0.85:.1f}", None),
            ("Radio oído", f"{d_.hear_radius} pasos", None),
            ("Error oído", f"±{d_.hear_error} tiles", None),
            ("Búsqueda", f"{d_.search_time:.0f}s (resta {max(0, mon.search_left):.1f})", None),
            ("Escuchando", f"{max(0, mon.idle):.1f}s quieto", None),
            ("Caza", "activa" if world.time >= d_.grace else f"en {d_.grace - world.time:.1f}s", None),
            ("Dist. recta", f"{dist_line:.1f} tiles", None),
            ("Dist. pasillo", f"{corr} pasos" if corr is not None else ">14 pasos", None),
            ("Te oyó", f"{mon.heard_count} veces", None),
            ("Paso cada", f"{STEP_STRIDE} tiles", None),
            ("Niebla", f"{world.fog * 100:.0f}% (desde {FOG_RANGE:.0f})", None),
        ]
        col_b = [
            ("IA / ALGORITMO", None, None),
            ("Algoritmo", d_.algorithm.upper(), (120, 255, 190)),
            ("", info[0], C_DIM),
            ("Frontera", info[1], None),
            ("Calidad", info[2], None),
            ("Replanes", str(mon.replans), None),
            ("Último plan", f"{mon.last_path_len} pasos", None),
            ("Costo plan", f"{plan['cost']:.2f}" if plan and plan["cost"] != float("inf") else "—", None),
            ("Nodos (último)", str(mon.last_expanded), None),
            ("Nodos (total)", str(mon.total_expanded), None),
            ("Nodos/replan", f"{mon.total_expanded / max(1, mon.replans):.1f}", None),
            ("Creencia", "concentrada" if informative else "uniforme", None),
            ("Pico creen.", f"({pk[0]}, {pk[1]}) {mon.belief[peak] * 100:.1f}%" if informative else "—", C_PEAK),
            ("σ / difusión", f"{d_.belief_sigma} / {d_.diffusion}", None),
            ("Percibió", f"({mon.perceived[0]}, {mon.perceived[1]})" if mon.perceived else "—", (90, 170, 255)),
            ("Mundo", f"{m.w}x{m.h} · sem {world.seed}", None),
            ("Ruidos hechos", str(world.noises_made), None),
        ]
        colw = (SCREEN_W - rx - 12) // 2
        for ci, rows in enumerate((col_a, col_b)):
            x0 = rx + ci * colw
            y = 12
            for label, val, col in rows:
                if val is None:                              # encabezado
                    screen.blit(font.render(label, True, (255, 90, 90)), (x0, y))
                    y += 28
                    continue
                if label:
                    screen.blit(small.render(label, True, C_DIM), (x0, y))
                value_x = x0 + (100 if label else 0)
                max_width = max(0, colw - (value_x - x0) - 8)
                shown_val = val
                while shown_val and small.size(shown_val)[0] > max_width:
                    shown_val = shown_val[:-2] + "…" if len(shown_val) > 2 else ""
                screen.blit(small.render(shown_val, True, col or C_TEXT), (value_x, y))
                y += 19
