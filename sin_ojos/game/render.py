"""Raycaster en primera persona (estilo Wolfenstein) con linterna y sprites."""
import math
import random
from collections import OrderedDict
from pathlib import Path

import pygame

from .config import RENDER_W, RENDER_H, FOV, LIGHT_DIST, FOG_LIGHT_LOSS

TEX = 64
SHADES = 32


class Renderer:
    def __init__(self, maze):
        self.grid = maze.grid
        self.doors = maze.doors
        self.room_tiles = maze.room_tiles
        self.wall_shades = self._build_walls()
        texture_path = Path(__file__).with_name("assets") / "wood_floor.png"
        self.wood_texture = pygame.transform.smoothscale(
            pygame.image.load(str(texture_path)).convert(), (TEX, TEX))
        self.door_shades = self._build_shades(self.wood_texture)
        self.backdrop = self._build_backdrop()
        self.vignette = self._build_vignette()
        self.monster_sprites = [self._build_monster(i * 2 * math.pi / 12) for i in range(12)]
        self.monster_sprite = self.monster_sprites[0]
        self.pebble_sprite = self._build_pebble()
        self.weapon_sprite = self._build_weapon()
        self.exit_sprite = self._build_exit()
        self.hand_fps = 12
        self.hand_atlases = {}
        self.hand_frames = self._load_atlas("hand_atlas.png", 60)
        self.hold_frames = self._load_atlas("hold_atlas.png", 60)
        self.idlegun_frames = self._load_atlas("idlegun_atlas.png", 60)
        self.gunshot_frames = self._load_atlas("gunshot_atlas.png", 18)
        assets = Path(__file__).with_name("assets")
        self.throw_sprite = pygame.image.load(str(assets / "throw_bw.png")).convert_alpha()
        self.muzzle_glow = self._build_muzzle_glow()
        self.fog_layers = self._build_fog()
        self.camera_overlay = self._build_camera_overlay()
        self.zbuf = [0.0] * RENDER_W
        self._wall_column_cache = OrderedDict()
        self._wall_column_cache_limit = 8192
        self.floor_layer = pygame.Surface((RENDER_W, RENDER_H), pygame.SRCALPHA).convert_alpha()
        self._floor_key = None
        self._floor_frame = 0

    # ---------------------------------------------------------- recursos
    def _load_atlas(self, filename, frame_count):
        atlas = pygame.image.load(
            str(Path(__file__).with_name("assets") / filename)).convert_alpha()
        self.hand_atlases[filename] = atlas
        return [atlas.subsurface(((index % 6) * 128, (index // 6) * 230, 128, 230))
                for index in range(frame_count)]

    def _build_muzzle_glow(self):
        size = 80
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        for y in range(size):
            for x in range(size):
                distance = math.hypot(x - center[0], y - center[1]) / (size * 0.5)
                alpha = int(max(0.0, 1.0 - distance) ** 2 * 210)
                glow.set_at((x, y), (218, 24, 18, alpha))
        return glow

    def _build_walls(self):
        rng = random.Random(7)
        base = pygame.Surface((TEX, TEX))
        for y in range(TEX):
            off = 16 if (y // 16) % 2 else 0
            for x in range(TEX):
                mortar = (y % 16 < 2) or ((x + off) % 32 < 2)
                n = rng.randint(-14, 14)
                c = (34 + n // 2,) * 3 if mortar else (104 + n, 94 + n, 86 + n)
                base.set_at((x, y), tuple(max(0, min(255, v)) for v in c))
        return self._build_shades(base.convert())

    def _build_shades(self, base):
        shades = []
        for i in range(SHADES):
            f = i / (SHADES - 1)
            s = base.copy()
            s.fill((int(255 * f * 0.95), int(255 * f * 0.98), int(255 * f)),
                   special_flags=pygame.BLEND_MULT)
            shades.append(s)
        return shades

    def _build_backdrop(self):
        s = pygame.Surface((RENDER_W, RENDER_H))
        half = RENDER_H // 2
        for y in range(RENDER_H):
            if y < half:
                k = 1 - y / half
                c = (int(1 + 6 * k), int(1 + 6 * k), int(2 + 8 * k))
            else:
                k = (y - half) / half
                c = (int(1 + 24 * k), int(1 + 21 * k), int(2 + 19 * k))
            pygame.draw.line(s, c, (0, y), (RENDER_W, y))
        return s.convert()

    def _build_vignette(self):
        w, h = 96, 54
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range(w):
                dx, dy = (x / w - 0.5) * 2, (y / h - 0.5) * 2
                r = math.sqrt(dx * dx * 0.8 + dy * dy * 1.1)
                a = int(max(0.0, min(1.0, (r - 0.3) * 1.35)) * 235)
                s.set_at((x, y), (0, 0, 0, a))
        return pygame.transform.smoothscale(s, (RENDER_W, RENDER_H)).convert_alpha()

    def _build_camera_overlay(self):
        overlay = pygame.Surface((RENDER_W, RENDER_H), pygame.SRCALPHA)
        for y in range(2, RENDER_H, 4):
            pygame.draw.line(overlay, (0, 0, 0, 18), (0, y), (RENDER_W, y))
        color = (190, 195, 190, 75)
        inset, length = 8, 12
        for x, direction in ((inset, 1), (RENDER_W - inset - 1, -1)):
            for y, vertical in ((inset, 1), (RENDER_H - inset - 1, -1)):
                pygame.draw.line(overlay, color, (x, y), (x + direction * length, y), 1)
                pygame.draw.line(overlay, color, (x, y), (x, y + vertical * length), 1)
        pygame.draw.circle(overlay, (220, 48, 42, 220), (18, 19), 3)
        overlay.blit(pygame.font.Font(None, 14).render("REC", True, (220, 48, 42)), (25, 13))
        pygame.draw.rect(overlay, color, (RENDER_W - 37, 14, 23, 10), 1)
        pygame.draw.rect(overlay, color, (RENDER_W - 14, 17, 2, 4))
        pygame.draw.rect(overlay, (190, 195, 190, 125), (RENDER_W - 34, 17, 14, 4))
        return overlay

    def _build_fog(self):
        """Niebla: un degradado centrado en el horizonte + dos capas de nubes que se desplazan."""
        W, H = RENDER_W, RENDER_H
        rng = random.Random(11)
        grad = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(H):
            k = (y - H / 2) / (H * 0.30)
            a = int(255 * (0.30 + 0.70 * math.exp(-k * k)))
            pygame.draw.line(grad, (78, 82, 90, a), (0, y), (W, y))
        clouds = []
        for cw, ch in ((13, 5), (27, 9)):
            small = pygame.Surface((cw, ch), pygame.SRCALPHA)
            for y in range(ch):
                for x in range(cw):
                    small.set_at((x, y), (118, 122, 130, int(rng.random() ** 1.4 * 255)))
            clouds.append(pygame.transform.smoothscale(small, (W * 2, H)).convert_alpha())
        return grad.convert_alpha(), clouds

    def _draw_fog(self, surf, fog, t):
        if fog < 0.02:
            return
        W, H = RENDER_W, RENDER_H
        grad, clouds = self.fog_layers
        grad.set_alpha(int(150 * fog))
        surf.blit(grad, (0, 0))
        # nubes que van y vienen a distinta velocidad (sin saltos al reiniciar)
        for i, (cl, spd) in enumerate(zip(clouds, (0.11, 0.19))):
            off = int(W * 0.5 * (1 + math.sin(t * spd + i * 2.1)))
            cl.set_alpha(int((105 + 55 * i) * fog))
            surf.blit(cl, (0, 0), (off, 0, W, H))

    def _build_monster(self, phase):
        s = pygame.Surface((64, 128), pygame.SRCALPHA)
        stride = math.sin(phase)
        lean = round(stride * 2)
        bob = round((1 - math.cos(phase * 2)) * 1.5)
        arm_swing = round(stride * 5)
        arm_drop = round((1 - math.cos(phase)) * 2)
        rim, body = (58, 52, 60, 255), (6, 5, 7, 255)
        shapes = [
            ("rect", (24 + round(stride * 2), 88 + bob, 6, 40)),
            ("rect", (34 - round(stride * 2), 88 + bob, 6, 40)),
            ("poly", [(22 + lean, 34 + bob), (42 + lean, 34 + bob),
                      (39 + lean, 92 + bob), (25 + lean, 92 + bob)]),
            ("line", (23 + lean, 38 + bob), (7 + arm_swing, 104 + bob + arm_drop)),
            ("line", (41 + lean, 38 + bob), (57 - arm_swing, 104 + bob + arm_drop)),
            ("ellipse", (24 + lean, 4 + bob, 16, 36)),
            ("poly", [(25 + lean, 16 + bob), (9 + lean, 4 + bob), (23 + lean, 30 + bob)]),
            ("poly", [(39 + lean, 16 + bob), (55 + lean, 4 + bob), (41 + lean, 30 + bob)]),
        ]
        for color, width in ((rim, 3), (body, 0)):
            for shape in shapes:
                kind, *coords = shape
                if kind == "rect":
                    pygame.draw.rect(s, color, coords[0], width)
                elif kind == "poly":
                    pygame.draw.polygon(s, color, coords[0], width)
                elif kind == "ellipse":
                    pygame.draw.ellipse(s, color, coords[0], width)
                else:
                    pygame.draw.line(s, color, coords[0], coords[1], 5 if width == 0 else 7)
        return s

    def _build_pebble(self):
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (8, 9, 13, 110), (3, 22, 26, 7))
        pygame.draw.ellipse(s, (76, 80, 90, 255), (5, 6, 22, 20))
        pygame.draw.ellipse(s, (139, 143, 151, 255), (9, 8, 12, 9))
        pygame.draw.line(s, (39, 42, 49, 255), (11, 12), (15, 20), 2)
        pygame.draw.line(s, (39, 42, 49, 255), (15, 20), (22, 15), 2)
        pygame.draw.circle(s, (184, 188, 195, 220), (11, 10), 2)
        return s

    def _build_weapon(self):
        path = Path(__file__).with_name("assets") / "handgun.png"
        image = pygame.image.load(str(path)).convert_alpha()
        bounds = image.get_bounding_rect(min_alpha=8)
        return image.subsurface(bounds).copy()

    def _build_exit(self):
        w, h = 48, 96
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(w):
            fx = max(0.0, min(1.0, (1 - abs((x - w / 2) / (w / 2))) * 1.6))
            for y in range(h):
                fy = max(0.0, min(1.0, (1 - abs((y - h / 2) / (h / 2))) * 1.3)) ** 0.6
                s.set_at((x, y), (170, 255, 190, int(255 * fx * fy)))
        return s

    # ---------------------------------------------------------- dibujo
    def render(self, surf, world, selected_slot=0):
        surf.blit(self.backdrop, (0, 0))
        t = world.time
        flick = 0.94 + 0.04 * math.sin(t * 13.0) * math.sin(t * 4.7) + 0.02 * math.sin(t * 31.0)
        if int(t * 2.3) % 17 == 0 and (t * 2.3) % 1 < 0.12:       # parpadeo ocasional
            flick *= 0.55
        px, py = world.px, world.py
        dx, dy = math.cos(world.angle), math.sin(world.angle)
        plx, ply = -dy * FOV, dx * FOV
        grid, z, shades = self.grid, self.zbuf, self.wall_shades
        W, H = RENDER_W, RENDER_H
        fog = getattr(world, "fog", 0.0)
        light = LIGHT_DIST * (1.0 - FOG_LIGHT_LOSS * fog)      # con niebla se ve menos lejos

        for x in range(W):
            cam = 2.0 * x / W - 1.0
            rdx, rdy = dx + plx * cam, dy + ply * cam
            mx, my = int(px), int(py)
            ddx = abs(1.0 / rdx) if rdx else 1e30
            ddy = abs(1.0 / rdy) if rdy else 1e30
            if rdx < 0:
                sx, sdx = -1, (px - mx) * ddx
            else:
                sx, sdx = 1, (mx + 1.0 - px) * ddx
            if rdy < 0:
                sy, sdy = -1, (py - my) * ddy
            else:
                sy, sdy = 1, (my + 1.0 - py) * ddy
            while True:
                if sdx < sdy:
                    sdx += ddx
                    mx += sx
                    side = 0
                else:
                    sdy += ddy
                    my += sy
                    side = 1
                if grid[my][mx]:
                    break
            perp = (sdx - ddx) if side == 0 else (sdy - ddy)
            if perp < 0.05:
                perp = 0.05
            z[x] = perp
            f = 1.0 - perp / light
            if f <= 0:
                continue
            f = f * f * flick * (0.72 if side else 1.0)
            idx = min(SHADES - 1, int(f * (SHADES - 1) + 0.5))
            if idx <= 0:
                continue
            wx = (py + perp * rdy) if side == 0 else (px + perp * rdx)
            wx -= math.floor(wx)
            tx = int(wx * TEX)
            if (side == 0 and rdx > 0) or (side == 1 and rdy < 0):
                tx = TEX - 1 - tx
            line_h = int(H / perp)
            y0 = H // 2 - line_h // 2
            v0, v1 = max(y0, 0), min(y0 + line_h, H)
            if v1 <= v0:
                continue
            s0 = int((v0 - y0) * TEX / line_h)
            s1 = int((v1 - y0) * TEX / line_h)
            wall = self.door_shades if (mx, my) in self.doors else shades
            wall_shade = wall[idx]
            cache_key = (id(wall_shade), tx, s0, s1, v1 - v0)
            col = self._wall_column_cache.get(cache_key)
            if col is None:
                source = wall_shade.subsurface((tx, s0, 1, max(1, s1 - s0)))
                col = pygame.transform.scale(source, (1, v1 - v0))
                self._wall_column_cache[cache_key] = col
                if len(self._wall_column_cache) > self._wall_column_cache_limit:
                    self._wall_column_cache.popitem(last=False)
            else:
                self._wall_column_cache.move_to_end(cache_key)
            surf.blit(col, (x, v0))

        floor_key = (round(px, 2), round(py, 2), round(dx, 2), round(dy, 2), round(light))
        self._floor_frame += 1
        if floor_key != self._floor_key and (self._floor_key is None or self._floor_frame % 3 == 0):
            self.floor_layer.fill((0, 0, 0, 0))
            self._draw_floor(self.floor_layer, world, px, py, dx, dy, plx, ply, light)
            self._floor_key = floor_key
        surf.blit(self.floor_layer, (0, 0))
        self._draw_fog(surf, fog, t)                  # la niebla va delante de las paredes...
        sprites = []
        mx_, my_ = world.monster.pos
        monster_frame = self.monster_sprites[int(t * 9) % len(self.monster_sprites)]
        if t < world.monster.incapacitated_until:
            monster_frame = monster_frame.copy()
            monster_frame.fill((150, 190, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
        sprites.append((math.hypot(mx_ - px, my_ - py), "m", mx_, my_, 0.0, monster_frame, 1.0))
        exit_x, exit_y = world.exit[0] + 0.5, world.exit[1] + 0.5
        sprites.append((math.hypot(exit_x - px, exit_y - py), "e", exit_x, exit_y, 0.0,
                        self.exit_sprite, 1.0))
        for pebble in world.pebble_projectiles:
            progress = min(1.0, pebble["elapsed"] / pebble["duration"])
            start, end = pebble["start"], pebble["end"]
            sx_ = start[0] + (end[0] - start[0]) * progress
            sy_ = start[1] + (end[1] - start[1]) * progress
            arc = math.sin(math.pi * progress) * 0.75 if not pebble["landed"] else 0.0
            age = max(0.0, pebble["elapsed"] - pebble["duration"])
            opacity = max(0.0, 1.0 - age / 8.0) if pebble["landed"] else 1.0
            sprites.append((math.hypot(sx_ - px, sy_ - py), "p", sx_, sy_, arc,
                            self.pebble_sprite, opacity))
        for tile in world.stone_pickups:
            sx_, sy_ = tile[0] + 0.5, tile[1] + 0.5
            sprites.append((math.hypot(sx_ - px, sy_ - py), "s", sx_, sy_, 0.0,
                            self.pebble_sprite, 1.0))
        for tile in world.weapon_pickups:
            sx_, sy_ = tile[0] + 0.5, tile[1] + 0.5
            sprites.append((math.hypot(sx_ - px, sy_ - py), "w", sx_, sy_, 0.0,
                            self.weapon_sprite, 1.0))
        for _, kind, sx_, sy_, vertical_offset, image, opacity in sorted(
                sprites, key=lambda sprite: sprite[0], reverse=True):
            if kind == "m":
                self._sprite(surf, image, sx_, sy_, px, py, dx, dy, plx, ply, 1.35, 1.0, flick)
            elif kind == "e":
                self._sprite(surf, image, sx_, sy_, px, py, dx, dy, plx, ply, 0.9, 2.2, 1.0)
            elif kind in ("s", "w"):
                self._sprite(surf, image, sx_, sy_, px, py, dx, dy, plx, ply,
                             0.3, 1.8, 1.0)
            else:
                self._sprite(surf, image, sx_, sy_, px, py, dx, dy, plx, ply,
                             0.17, 1.8, 1.0, vertical_offset, opacity)
        self._draw_fog(surf, fog * 0.3, t)            # ...y una pasada ligera sobre el monstruo
        surf.blit(self.vignette, (0, 0))
        self._draw_hand(surf, world, t, selected_slot)
        surf.blit(self.camera_overlay, (0, 0))

    def _ping_pong_frame(self, frames, time):
        last_frame = len(frames) - 1
        phase = int(time * self.hand_fps) % (last_frame * 2)
        frame_index = phase if phase <= last_frame else last_frame * 2 - phase
        return frames[frame_index]

    def _blit_hand(self, surf, frame):
        surf.blit(frame, (RENDER_W - frame.get_width() - 4,
                          RENDER_H - frame.get_height() + 20))

    def _draw_hand(self, surf, world, time, selected_slot):
        if world.hand_action == "throw" and time < world.hand_action_until:
            frame = self.throw_sprite
        elif world.hand_action == "gunshot" and time < world.hand_action_until:
            frame_index = min(len(self.gunshot_frames) - 1,
                              int((time - world.hand_action_started) * self.hand_fps))
            frame = self.gunshot_frames[frame_index]
        elif selected_slot == 0 and world.pebbles > 0:
            frame = self._ping_pong_frame(self.hold_frames, time)
        elif selected_slot == 1:
            frame = self._ping_pong_frame(self.idlegun_frames, time)
        else:
            frame = self._ping_pong_frame(self.hand_frames, time)
        self._blit_hand(surf, frame)
        if time < world.muzzle_flash_until:
            intensity = min(1.0, (world.muzzle_flash_until - time) / 0.06)
            self.muzzle_glow.set_alpha(int(230 * intensity))
            surf.blit(self.muzzle_glow, (RENDER_W - 146, RENDER_H - 166))

    def _draw_floor(self, surf, world, px, py, dx, dy, plx, ply, light):
        """Proyecta el sombreado de cada tile sobre el suelo visible."""
        horizon, step = RENDER_H // 2, 8
        z = self.zbuf
        grid = self.grid
        for y in range(horizon + 2, RENDER_H - step + 1, step):
            row_dist = (RENDER_H * 0.5) / (y - horizon)
            if row_dist >= light:
                continue
            lit = (1.0 - row_dist / light) ** 2
            for x in range(0, RENDER_W, step):
                if row_dist >= z[x]:
                    continue
                cam = 2.0 * x / RENDER_W - 1.0
                world_x = px + row_dist * (dx + plx * cam)
                world_y = py + row_dist * (dy + ply * cam)
                fx, fy = int(world_x), int(world_y)
                if not (0 <= fy < len(grid) and 0 <= fx < len(grid[0])) or grid[fy][fx]:
                    continue
                tile = (fx, fy)
                shade = world.floor_darkness.get(tile, 0.0)
                if tile in world.noisy:
                    shade = min(0.55, shade + 0.055)
                if tile in self.room_tiles:
                    tx, ty = int(world_x * TEX) % TEX, int(world_y * TEX) % TEX
                    texture_color = self.wood_texture.get_at((tx, ty))
                    factor = (0.08 + 0.20 * lit) * (1 - shade)
                    color = tuple(int(channel * factor) for channel in texture_color[:3])
                else:
                    value = max(0, min(255, int((3 + 21 * lit) * (1 - shade))))
                    color = (value, value, min(255, value + 1))
                pygame.draw.rect(surf, color,
                                 (x, y, min(step, RENDER_W - x), min(step, RENDER_H - y)))

    def _sprite(self, surf, img, sx, sy, px, py, dx, dy, plx, ply, hscale, fade_reach, flick,
                vertical_offset=0.0, opacity=1.0):
        rx, ry = sx - px, sy - py
        inv = 1.0 / (plx * dy - dx * ply)
        tx = inv * (dy * rx - dx * ry)
        ty = inv * (-ply * rx + plx * ry)
        if ty <= 0.15:
            return
        W, H = RENDER_W, RENDER_H
        sh = int(H / ty * hscale)
        if sh < 2 or sh > 1800:
            return
        sw = max(1, int(sh * img.get_width() / img.get_height()))
        x0 = int(W / 2 * (1 + tx / ty)) - sw // 2
        y0 = H // 2 + int(H / ty / 2) - sh - int(H * vertical_offset / ty)
        z = self.zbuf
        cols = [c for c in range(max(0, x0), min(W, x0 + sw)) if z[c] > ty]
        if not cols:
            return
        a = max(0.0, min(1.0, 1.0 - ty / (LIGHT_DIST * fade_reach))) ** 1.3 * flick * opacity
        if a <= 0.02:
            return
        scaled = pygame.transform.scale(img, (sw, sh))
        scaled.set_alpha(int(255 * min(1.0, a)))
        for c in cols:
            surf.blit(scaled, (c, y0), (c - x0, 0, 1, sh))
