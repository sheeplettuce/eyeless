"""Lógica del juego, sin pygame (así se puede simular sin ventana)."""
import math
import random
from dataclasses import dataclass

from .config import (WALK_SPEED, SPRINT_FACTOR, SPRINT_DRAIN, SPRINT_REGEN, SPRINT_MAX,
                     SPRINT_NOISE_FACTOR, PLAYER_RADIUS, CATCH_RADIUS, PEBBLE_RANGE,
                     STEP_STRIDE, STEP_HEAR_RANGE, FOG_RANGE, FOG_RISE,
                     BLUE_POINT_INTERVAL, SHOUT_RANGE_FACTOR, SPRINT_MONSTER_MARGIN,
                     PEBBLE_PICKUP_COUNT, WEAPON_PICKUP_COUNT, WEAPON_RANGE,
                     WEAPON_HIT_RADIUS, WEAPON_STUN_DURATION)
from .maze import generate
from .monster import Monster
from .noisemap import build_floor_darkness, build_noise_tiles

PLAYING, WON, LOST = "playing", "won", "lost"


@dataclass
class NoiseEvent:
    tile: tuple
    radius: int
    kind: str
    time: float
    heard: bool


class World:
    def __init__(self, diff, seed=None):
        self.diff = diff
        self.seed = random.randrange(1_000_000) if seed is None else seed
        rng = random.Random(self.seed)
        self.maze = generate(diff.cells, diff.braid, rng)
        self.start = (1, 1)
        dist = self.maze.bfs_dist(self.start)
        far = max(dist.values())
        self.exit = rng.choice([t for t, d in dist.items() if d == far])
        self.exit_distances = self.maze.bfs_dist(self.exit)
        exclude = {self.start, self.exit} | set(self.maze.adj[self.start])
        self.noisy = build_noise_tiles(self.maze, diff.noise_density, self.seed, exclude)
        self.floor_darkness = build_floor_darkness(self.maze, self.seed)

        mstart = rng.choice([t for t, d in dist.items() if far * 0.45 <= d <= far * 0.75])
        self.monster = Monster(self.maze, diff, mstart, random.Random(self.seed + 17))
        self.monster.deaf_until = diff.grace

        self.px, self.py = self.start[0] + 0.5, self.start[1] + 0.5
        self.angle = 0.0 if (2, 1) in self.maze.adj[self.start] else math.pi / 2
        self.moving = False
        self.sprinting = False
        self.stamina = SPRINT_MAX
        self.pebbles = diff.pebbles

        self.time = 0.0
        self.state = PLAYING
        self.end_time = 0.0
        self.events = []            # eventos de audio para la capa pygame
        self.noise_log = []
        self.noise_flash = 0.0
        self.noises_made = 0
        self.player_tile = self.start
        self.explored = set()
        self.revealed_noisy = set()
        self.mon_dist = None
        self._mon_timer = 0.0
        self._hb_timer = 0.0
        self.fog = 0.0              # 0..1: niebla que se cierra cuando el monstruo está cerca
        self._step_acc = 0.0
        self._last_mon_pos = self.monster.pos
        self._fx_rng = random.Random(self.seed + 91)
        self._fx_timer = 0.0
        self._player_breath_timer = 0.0
        self._breath_pressure = 0.0
        self._voice_rng = random.Random(self.seed + 251)
        self._voice_timer = self._voice_rng.uniform(5.0, 10.0)
        self.pebble_projectiles = []
        self._points_rng = random.Random(self.seed + 193)
        self._points_timer = BLUE_POINT_INTERVAL
        self.blue_points = set()
        self._spawn_blue_points(self._blue_point_batch_size())
        self._spawn_pickups(rng)
        self.ammo = 0

    # ------------------------------------------------------------ jugador
    def _blocked(self, x, y):
        r, g = PLAYER_RADIUS, self.maze.grid
        for cx in (x - r, x + r):
            for cy in (y - r, y + r):
                if not (0 <= int(cx) < self.maze.w and 0 <= int(cy) < self.maze.h):
                    return True
                if g[int(cy)][int(cx)]:
                    return True
        return False

    def move_player(self, vx, vy, sprint, dt):
        n = math.hypot(vx, vy)
        self.moving = n > 1e-6
        can_move = self.moving and self.state == PLAYING
        sprint_time = min(dt, self.stamina / SPRINT_DRAIN) if sprint and can_move else 0.0
        self.sprinting = sprint_time > 0
        if self.sprinting:
            self.stamina = max(0.0, self.stamina - SPRINT_DRAIN * sprint_time)
        else:
            self.stamina = min(SPRINT_MAX, self.stamina + SPRINT_REGEN * dt)
        if not can_move:
            return
        sprint_speed = max(WALK_SPEED * SPRINT_FACTOR,
                           self.diff.monster_speed * SPRINT_MONSTER_MARGIN)
        distance = WALK_SPEED * (dt - sprint_time) + sprint_speed * sprint_time
        dx, dy = vx / n * distance, vy / n * distance
        steps = max(1, math.ceil(distance / 0.1))
        dx, dy = dx / steps, dy / steps
        for _ in range(steps):
            moved = False
            if not self._blocked(self.px + dx, self.py):
                self.px += dx
                moved = True
            if not self._blocked(self.px, self.py + dy):
                self.py += dy
                moved = True
            if not moved:
                break

    def throw_pebble(self):
        if self.state != PLAYING or self.pebbles <= 0:
            return False
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        d, last = 0.0, (self.px, self.py)
        while d < PEBBLE_RANGE:
            d += 0.1
            x, y = self.px + dx * d, self.py + dy * d
            if self.maze.grid[int(y)][int(x)]:
                break
            last = (x, y)
        self.pebbles -= 1
        distance = math.hypot(last[0] - self.px, last[1] - self.py)
        self.pebble_projectiles.append({
            "start": (self.px, self.py),
            "end": last,
            "duration": max(0.25, distance / 9.0),
            "elapsed": 0.0,
            "landed": False,
        })
        return True

    def shoot_weapon(self):
        if self.state != PLAYING or self.ammo <= 0:
            return False
        self.ammo -= 1
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        mx, my = self.monster.pos
        rx, ry = mx - self.px, my - self.py
        along = rx * dx + ry * dy
        across = abs(rx * dy - ry * dx)
        hit = 0.0 <= along <= WEAPON_RANGE and across <= WEAPON_HIT_RADIUS
        if hit:
            distance = 0.0
            while distance < along:
                distance += 0.05
                x, y = self.px + dx * distance, self.py + dy * distance
                if self.maze.grid[int(y)][int(x)]:
                    hit = False
                    break
        if hit:
            self.monster.incapacitate(self.time, WEAPON_STUN_DURATION[self.diff.key])
        self.emit_noise(self.player_tile, max(12, self.diff.hear_radius + 8), "disparo")
        self.events.append(("gunshot", 1.0, 0.0, 1.0))
        return True

    # ------------------------------------------------------------ ruido
    def emit_noise(self, tile, radius, kind):
        exact_target = self.player_tile if kind != "piedra" else None
        heard = self.monster.hear(tile, radius, self.time, exact_target=exact_target)
        self.noise_log.append(NoiseEvent(tile, radius, kind, self.time, heard))
        del self.noise_log[:-10]

    def shout(self):
        if self.state != PLAYING:
            return False
        radius = max(self.diff.hear_radius + 1,
                     round(self.diff.hear_radius * SHOUT_RANGE_FACTOR))
        self.emit_noise(self.player_tile, radius, "grito")
        self.events.append(("shout", 1.0, 0.0, 1.0))
        return True

    def exit_hint(self):
        tile = self.player_tile
        distance = self.exit_distances[tile]
        if distance == 0:
            return "¡La salida está aquí!"
        next_tile = min(self.maze.adj[tile], key=self.exit_distances.__getitem__)
        dx = next_tile[0] - tile[0]
        dy = next_tile[1] - tile[1]
        relative = (math.atan2(dy, dx) - self.angle + math.pi) % (2 * math.pi) - math.pi
        if abs(relative) < math.pi / 4:
            direction = "al frente"
        elif relative > 3 * math.pi / 4 or relative < -3 * math.pi / 4:
            direction = "atrás"
        elif relative > 0:
            direction = "a la derecha"
        else:
            direction = "a la izquierda"
        return f"Salida: {distance} pasos, {direction}"

    def _on_enter_tile(self, tile):
        inten = self.noisy.get(tile)
        if inten is None:
            return
        self.revealed_noisy.add(tile)
        radius = max(4, round(self.diff.hear_radius * inten *
                              (SPRINT_NOISE_FACTOR if self.sprinting else 1.0)))
        self.noises_made += 1
        self.noise_flash = 1.0
        self.events.append(("creak", 0.45 + 0.4 * inten, 0.0))
        self.emit_noise(tile, radius, "paso")

    def _bearing_pan(self, x, y):
        dx, dy = x - self.px, y - self.py
        front = dx * math.cos(self.angle) + dy * math.sin(self.angle)
        side = dx * -math.sin(self.angle) + dy * math.cos(self.angle)
        angle = math.atan2(side, front)
        return math.sin(angle), math.cos(angle)

    def _update_pebbles(self, dt):
        for pebble in self.pebble_projectiles:
            pebble["elapsed"] += dt
            if not pebble["landed"] and pebble["elapsed"] >= pebble["duration"]:
                pebble["landed"] = True
                x, y = pebble["end"]
                tile = (int(x), int(y))
                self.emit_noise(tile, self.diff.hear_radius + 8, "piedra")
                pan, front = self._bearing_pan(x, y)
                self.events.append(("pebble", 0.0, pan, front))
        self.pebble_projectiles[:] = [
            pebble for pebble in self.pebble_projectiles
            if not pebble["landed"] or pebble["elapsed"] < pebble["duration"] + 8.0
        ]

    # ------------------------------------------------------------ bucle
    def update(self, dt):
        if self.state != PLAYING:
            self.end_time += dt
            return
        self.time += dt
        self.noise_flash = max(0.0, self.noise_flash - dt * 1.5)
        self._update_pebbles(dt)
        self._points_timer -= dt
        while self._points_timer <= 0:
            self._spawn_blue_points(self._blue_point_batch_size())
            self._points_timer += BLUE_POINT_INTERVAL

        tile = (int(self.px), int(self.py))
        if tile != self.player_tile:
            self.player_tile = tile
            self._on_enter_tile(tile)
        self._collect_pickups()
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                t = (tile[0] + dx, tile[1] + dy)
                if 0 <= t[0] < self.maze.w and 0 <= t[1] < self.maze.h:
                    self.explored.add(t)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                t = (tile[0] + dx, tile[1] + dy)
                if t in self.noisy:
                    self.revealed_noisy.add(t)

        self.monster.update(dt, self.time, self.player_tile)

        self._voice_timer -= dt
        if self._voice_timer <= 0:
            distances = self.maze.bfs_dist(self.player_tile)
            voice_distance = distances.get(self.monster.here, len(self.maze.floor))
            max_distance = max(1, max(self.exit_distances.values()))
            proximity = max(0.0, 1.0 - voice_distance / max_distance)
            pan, front = self._bearing_pan(*self.monster.pos)
            self.events.append(("monster_voice", self._voice_rng.randrange(10),
                                0.24 + 0.40 * proximity, pan, front))
            self._voice_timer = self._voice_rng.uniform(12.0, 22.0)

        # --- audio: pasos y latidos del monstruo, por distancia de pasillo
        self._mon_timer -= dt
        if self._mon_timer <= 0:
            self._mon_timer = 0.15
            self.mon_dist = self.maze.bfs_dist(self.player_tile,
                                               limit=STEP_HEAR_RANGE).get(self.monster.here)
        mx, my = self.monster.pos
        self._player_breath_timer -= dt
        if self.sprinting:
            self._breath_pressure = min(1.0, self._breath_pressure + dt * 0.75)
        else:
            self._breath_pressure = max(0.0, self._breath_pressure - dt * 0.22)
        if self._breath_pressure > 0.12 and self._player_breath_timer <= 0:
            self.events.append(("player_breath", self._breath_pressure, 0.0, 1.0))
            self._player_breath_timer = 0.85 - self._breath_pressure * 0.2

        self._fx_timer -= dt
        if self.mon_dist is not None and self.mon_dist <= 10:
            if self._fx_timer <= 0:
                close = max(0.0, min(1.0, 1.0 - self.mon_dist / 11.0))
                pan, front = self._bearing_pan(mx, my)
                roar_mix = max(0.0, min(1.0, (7.0 - self.mon_dist) / 5.0))
                breath_level = close * (1.0 - 0.65 * roar_mix)
                self.events.append(("monster_breath", breath_level, pan, front))
                if roar_mix > 0.05:
                    self.events.append(("monster_roar", close * roar_mix, pan, front))
                if roar_mix >= 0.5:
                    self._fx_timer = self._fx_rng.uniform(1.7, 2.8)
                elif self._fx_rng.random() < 0.75:
                    self._fx_timer = self._fx_rng.uniform(2.0, 3.5)
                else:
                    self.events.append(("scrape", close, pan, front))
                    self._fx_timer = self._fx_rng.uniform(2.5, 4.0)
        else:
            self._fx_timer = min(self._fx_timer, 0.5)
        # un paso cada STEP_STRIDE tiles recorridos (no uno por tile): se oye su ritmo
        self._step_acc += math.hypot(mx - self._last_mon_pos[0], my - self._last_mon_pos[1])
        self._last_mon_pos = (mx, my)
        while self._step_acc >= STEP_STRIDE:
            self._step_acc -= STEP_STRIDE
            d = self.mon_dist
            if d is not None and d <= STEP_HEAR_RANGE:
                loud = 1.0 - d / (STEP_HEAR_RANGE + 1.0)
                pan, front = self._bearing_pan(mx, my)
                self.events.append(("step", loud, pan, front))
        self._hb_timer -= dt
        if self.mon_dist is not None and self.mon_dist <= 7 and self._hb_timer <= 0:
            close = 1.0 - self.mon_dist / 8.0
            self.events.append(("heart", close, 0.0))
            self._hb_timer = 1.1 - 0.65 * close

        # --- niebla: se cierra al acercarse el monstruo y se disipa al alejarse
        target = 0.0
        if self.mon_dist is not None:
            target = max(0.0, min(1.0, 1.0 - self.mon_dist / FOG_RANGE)) ** 0.85
        self.fog += (target - self.fog) * min(1.0, dt * FOG_RISE)

        # --- fin de partida
        if (self.time >= self.monster.incapacitated_until
                and math.hypot(mx - self.px, my - self.py) < CATCH_RADIUS):
            self.state = LOST
            return
        ex, ey = self.exit[0] + 0.5, self.exit[1] + 0.5
        if math.hypot(ex - self.px, ey - self.py) < 0.6:
            self.state = WON

    def _blue_point_batch_size(self):
        return {"facil": 2, "medio": 3, "dificil": 4}[self.diff.key]

    def _spawn_blue_points(self, count):
        occupied = self.blue_points | set(self.noisy) | {self.start, self.exit}
        candidates = [tile for tile in self.maze.floor if tile not in occupied]
        self._points_rng.shuffle(candidates)
        self.blue_points.update(candidates[:count])

    def _spawn_pickups(self, rng):
        occupied = set(self.noisy) | self.blue_points | {self.start, self.exit, self.monster.here}
        candidates = [tile for tile in self.maze.floor if tile not in occupied]
        rng.shuffle(candidates)
        self.stone_pickups = set(candidates[:PEBBLE_PICKUP_COUNT])
        self.weapon_pickups = set(candidates[PEBBLE_PICKUP_COUNT:
                                              PEBBLE_PICKUP_COUNT + WEAPON_PICKUP_COUNT])

    def _collect_pickups(self):
        for pickups, item in ((self.stone_pickups, "stone"), (self.weapon_pickups, "weapon")):
            for tile in pickups.copy():
                if math.hypot(tile[0] + 0.5 - self.px, tile[1] + 0.5 - self.py) >= 0.5:
                    continue
                pickups.remove(tile)
                if item == "stone":
                    self.pebbles += 1
                else:
                    self.ammo += 1
