"""Ventana, menús, HUD y bucle principal."""
import math
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pygame

from .audio import Audio
from .config import (SCREEN_W, SCREEN_H, SPRINT_MAX, RENDER_W, RENDER_H, FPS,
                     DIFFICULTIES, BY_KEY, MAGAZINE_SIZE)
from .debug_view import DevView
from .render import Renderer
from .world import World, PLAYING, LOST

MENU, LOADING, PLAY, PAUSE, END = "menu", "loading", "play", "pause", "end"
FONT_NAME = pygame.font.match_font("Times New Roman") or None
MENU_FONT_FILE = Path(__file__).with_name("assets") / "EngraversMT.ttf"
MENU_FONT_NAME = (str(MENU_FONT_FILE) if MENU_FONT_FILE.is_file()
                  else pygame.font.match_font("Engravers MT")
                  or pygame.font.match_font("Bookman Old Style")
                  or FONT_NAME)


class App:
    def __init__(self, args):
        pygame.init()
        self.dev = getattr(args, "debug", False)     # modo dev (casilla / F1)
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("EYELESS")
        self.view = pygame.Surface((RENDER_W, RENDER_H)).convert()
        self.clock = pygame.time.Clock()
        self.f_big = pygame.font.Font(FONT_NAME, 84)
        self.f_mid = pygame.font.Font(FONT_NAME, 36)
        self.f = pygame.font.Font(FONT_NAME, 26)
        self.f_small = pygame.font.Font(FONT_NAME, 20)
        self.f_dev = pygame.font.Font(FONT_NAME, 19)
        self.menu_title_font = pygame.font.Font(MENU_FONT_NAME, 43)
        self.menu_option_font = pygame.font.Font(MENU_FONT_NAME, 25)
        self.menu_small_font = pygame.font.Font(MENU_FONT_NAME, 15)
        self.menu_desc_font = pygame.font.Font(FONT_NAME, 17)
        jumpscare_path = Path(__file__).with_name("assets") / "jumpscare.png"
        jumpscare_image = pygame.image.load(str(jumpscare_path)).convert()
        self.jumpscare_image = pygame.transform.smoothscale(
            jumpscare_image, (SCREEN_W, SCREEN_H))
        menu_path = Path(__file__).with_name("assets") / "menusito.png"
        menu_image = pygame.image.load(str(menu_path)).convert()
        self.menu_image = pygame.transform.smoothscale(menu_image, (360, 360))
        self.menu_image.fill((102, 102, 102), special_flags=pygame.BLEND_RGB_MULT)
        self.audio = Audio(enabled=not getattr(args, "silencio", False))
        self.running = True
        self.scene = MENU
        self.sel = 1
        self.devview = DevView()
        self.dev_box = pygame.Rect(SCREEN_W - 176, SCREEN_H - 72, 20, 20)   # abajo a la derecha
        self.show_map = True
        self.world = None
        self.renderer = None
        self._generation_executor = ThreadPoolExecutor(max_workers=1,
                                   thread_name_prefix="maze-generator")
        self._generation_future = None
        self._loading_diff = None
        self._loading_elapsed = 0.0
        self._loading_error = None
        self.selected_slot = 0
        self.seed_arg = getattr(args, "semilla", None)
        if getattr(args, "dificultad", None):
            self.sel = DIFFICULTIES.index(BY_KEY[args.dificultad])
            self.start_game()

    # ---------------------------------------------------------- flujo
    def start_game(self):
        diff = DIFFICULTIES[self.sel]
        seed = self.seed_arg
        self.seed_arg = None
        self.selected_slot = 0
        self._jumpscare_played = False
        self.world = None
        self.renderer = None
        self._loading_diff = diff
        self._loading_elapsed = 0.0
        self._loading_error = None
        self._generation_future = self._generation_executor.submit(World, diff, seed)
        self.scene = LOADING
        self._sync_window()
        self.audio.stop()
        self.grab(False)

    def _finish_generation(self):
        try:
            self.world = self._generation_future.result()
            self.renderer = Renderer(self.world.maze)
        except Exception as error:
            self._loading_error = str(error)
            self.scene = MENU
            self._generation_future = None
            return
        self.show_map = self._loading_diff.minimap != "off"
        self._generation_future = None
        self.scene = PLAY
        self.audio.ambient()
        self.grab(True)

    def draw_loading(self, dt):
        self._loading_elapsed += dt
        self.screen.fill((7, 8, 10))
        center = (SCREEN_W // 2, SCREEN_H // 2)
        self.text("GENERANDO LABERINTO", self.f, (190, 190, 195),
                  (center[0], center[1] - 25), center=True, shadow=False)
        track = pygame.Rect(center[0] - 110, center[1] + 20, 220, 4)
        pygame.draw.rect(self.screen, (44, 46, 50), track)
        segment_x = track.x + int((track.width - 55) *
                                  (0.5 + 0.5 * math.sin(self._loading_elapsed * 4.0)))
        pygame.draw.rect(self.screen, (165, 165, 170),
                         (segment_x, track.y, 55, track.height))

    def grab(self, on):
        pygame.event.set_grab(on)
        pygame.mouse.set_visible(not on)
        if on:
            pygame.mouse.get_rel()

    def to_menu(self):
        self.audio.stop()
        self.grab(False)
        self.scene = MENU
        self._sync_window()

    def _sync_window(self):
        if pygame.display.get_surface().get_size() != (SCREEN_W, SCREEN_H):
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    def toggle_dev(self):
        self.dev = not self.dev
        self._sync_window()

    # ---------------------------------------------------------- eventos
    def handle(self, e):
        if e.type == pygame.QUIT:
            self.running = False
            return
        if e.type == pygame.MOUSEBUTTONDOWN:
            if self.scene == PLAY and e.button == 1:
                if self.selected_slot == 1:
                    self.world.shoot_weapon()
                elif self.selected_slot == 0:
                    self.world.throw_pebble()
            elif self.scene == PLAY and e.button == 3:
                self.world.shout()
            elif e.button == 1 and self.dev_box.inflate(110, 8).collidepoint(e.pos):
                self.toggle_dev()
                return
        if e.type != pygame.KEYDOWN:
            return
        k = e.key
        if self.scene == MENU:
            if k in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % 3
            elif k in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % 3
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.sel = k - pygame.K_1
                self.start_game()
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_game()
            elif k == pygame.K_ESCAPE:
                self.running = False
        elif self.scene == PLAY:
            if k == pygame.K_ESCAPE:
                self.scene = PAUSE
                self.grab(False)
            elif pygame.K_1 <= k <= pygame.K_5:
                self.selected_slot = k - pygame.K_1
            elif k == pygame.K_SPACE:
                self.world.throw_pebble()
            elif k == pygame.K_f:
                self.world.shoot_weapon()
            elif k == pygame.K_r:
                self.world.reload_weapon()
            elif k == pygame.K_e:
                self.world.interact_door()
            elif k == pygame.K_TAB and self.world.diff.minimap != "off":
                self.show_map = not self.show_map
            elif k == pygame.K_F1:
                self.toggle_dev()
        elif self.scene == PAUSE:
            if k == pygame.K_ESCAPE:
                self.scene = PLAY
                self.grab(True)
            elif k == pygame.K_m:
                self.to_menu()
            elif k == pygame.K_F1:
                self.toggle_dev()
        elif self.scene == END:
            if k == pygame.K_RETURN:
                self.start_game()
            elif k in (pygame.K_m, pygame.K_ESCAPE):
                self.to_menu()
            elif k == pygame.K_F1:
                self.toggle_dev()

    # ---------------------------------------------------------- actualización
    def update_play(self, dt):
        w = self.world
        if self.scene == PLAY:
            keys = pygame.key.get_pressed()
            fwd = (keys[pygame.K_w] or keys[pygame.K_UP]) - (keys[pygame.K_s] or keys[pygame.K_DOWN])
            strafe = keys[pygame.K_d] - keys[pygame.K_a]
            turn = keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]
            rel = pygame.mouse.get_rel()[0]
            w.angle += turn * 2.2 * dt + rel * 0.0025
            ca, sa = math.cos(w.angle), math.sin(w.angle)
            sprint = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
            w.move_player(ca * fwd - sa * strafe, sa * fwd + ca * strafe, sprint, dt)
            w.update(dt)
            for ev in w.events:
                self.audio.handle(ev)
            w.events.clear()
            if w.state != PLAYING:
                self.scene = END
                self.audio.stop()
                if w.state == LOST and not self._jumpscare_played:
                    self.audio.handle(("jumpscare", 1.0, 0.0))
                    self._jumpscare_played = True
                self.grab(False)
        elif self.scene == END:
            w.update(dt)

    # ---------------------------------------------------------- dibujo
    def text(self, s, font, color, pos, center=False, shadow=True):
        img = font.render(s, True, color)
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        if shadow:
            self.screen.blit(font.render(s, True, (0, 0, 0)), r.move(2, 2))
        self.screen.blit(img, r)

    def draw_menu(self):
        s = self.screen
        s.fill((0, 0, 0))
        image_rect = self.menu_image.get_rect(topright=(SCREEN_W - 38, 40))
        pygame.draw.rect(s, (12, 12, 14), image_rect.inflate(12, 12), border_radius=3)
        pygame.draw.rect(s, (36, 36, 39), image_rect.inflate(12, 12), 1, border_radius=3)
        s.blit(self.menu_image, image_rect)
        self.text("EYELESS", self.menu_title_font, (185, 185, 190), (48, 61))
        self.text("NO PUEDE VERTE. SOLO PUEDE OÍRTE.", self.menu_small_font,
                  (122, 122, 128), (51, 119), shadow=False)
        descriptions = (
            "Persigue sin encontrar siempre el camino mas corto.",
            "Busca la ruta mas corta por los pasillos.",
            "Calcula una ruta segun donde cree que estas.",
        )
        for i, d in enumerate(DIFFICULTIES):
            y = 174 + i * 82
            on = i == self.sel
            col = (218, 218, 222) if on else (133, 133, 140)
            if on:
                pygame.draw.rect(s, (12, 12, 14), (39, y - 9, 490, 67), border_radius=2)
                pygame.draw.rect(s, (104, 35, 40), (39, y - 9, 2, 67))
            self.text(f"{i + 1}.  {d.label.upper()}", self.menu_option_font, col, (54, y))
            self.text(f"IA {d.algorithm.upper()}  /  {descriptions[i]}", self.menu_desc_font,
                      (134, 134, 140) if on else (100, 100, 106),
                      (57, y + 34), shadow=False)
        self.text("↑ / ↓   ELEGIR      ENTER   COMENZAR      ESC   SALIR",
                  self.menu_small_font, (130, 130, 136), (49, 435), shadow=False)
        self.text("WASD MOVER   ·   SHIFT CORRER   ·   ESPACIO PIEDRA   ·   E PUERTAS",
                  self.menu_small_font, (94, 94, 100), (49, 475), shadow=False)
        self.text("F / CLIC DISPARAR   ·   CLIC DERECHO GRITAR",
                  self.menu_small_font, (94, 94, 100), (49, 502), shadow=False)

    def draw_minimap(self):
        w = self.world
        m = w.maze
        mode = w.diff.minimap
        ts = 5
        ox = oy = 12
        bg = pygame.Surface((m.w * ts + 8, m.h * ts + 8), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 150))
        self.screen.blit(bg, (ox - 4, oy - 4))
        for y in range(m.h):
            for x in range(m.w):
                t = (x, y)
                if mode == "near" and t not in w.explored:
                    continue
                r = (ox + x * ts, oy + y * ts, ts, ts)
                if t in m.doors:
                    color = (54, 135, 101) if m.doors[t] else (145, 91, 48)
                    pygame.draw.rect(self.screen, color, r)
                elif m.grid[y][x]:
                    pygame.draw.rect(self.screen, (90, 90, 100), r)
                elif t == w.exit:
                    pygame.draw.rect(self.screen, (80, 230, 120), r)
                elif t in w.blue_points:
                    pygame.draw.rect(self.screen, (28, 28, 34), r)
                    pygame.draw.circle(self.screen, (65, 155, 255),
                                       (ox + x * ts + ts // 2, oy + y * ts + ts // 2), 2)
                elif t in w.noisy and (mode == "full" or t in w.revealed_noisy):
                    shade = min(0.55, w.floor_darkness.get(t, 0.0) + 0.055)
                    color = tuple(int(c * (1 - shade)) for c in (28, 28, 34))
                    pygame.draw.rect(self.screen, color, r)
                else:
                    shade = w.floor_darkness.get(t, 0.0)
                    color = tuple(int(c * (1 - shade)) for c in (28, 28, 34))
                    pygame.draw.rect(self.screen, color, r)
        px, py = ox + w.px * ts, oy + w.py * ts
        pygame.draw.circle(self.screen, (255, 255, 255), (px, py), 3)
        pygame.draw.line(self.screen, (255, 255, 255), (px, py),
                         (px + math.cos(w.angle) * 8, py + math.sin(w.angle) * 8), 1)

    def draw_hud(self):
        w = self.world
        mm, ss = divmod(int(w.time), 60)
        self.text(f"{mm:02d}:{ss:02d}", self.f_small, (170, 170, 180), (SCREEN_W - 70, 14))
        self.text(w.exit_hint(), self.f_small, (170, 210, 180),
                  (SCREEN_W // 2, 24), True)
        self.draw_inventory()
        stamina_rect = pygame.Rect(16, SCREEN_H - 22, 100, 10)
        pygame.draw.rect(self.screen, (32, 32, 38), stamina_rect)
        fill = stamina_rect.copy()
        fill.width = int(stamina_rect.width * w.stamina / SPRINT_MAX)
        pygame.draw.rect(self.screen, (70, 165, 255) if w.stamina > 25 else (220, 100, 70), fill)
        self.text("RESISTENCIA", self.f_small, (160, 190, 220),
                  (16, SCREEN_H - 48))
        if w.door_ahead() is not None:
            self.text("E: abrir / cerrar", self.f_small, (205, 175, 130),
                      (SCREEN_W - 180, SCREEN_H - 48))
        if w.noise_flash > 0:
            a = int(255 * min(1.0, w.noise_flash * 1.5))
            img = self.f_mid.render("¡ruido!", True, (230, 60, 60))
            img.set_alpha(a)
            self.screen.blit(img, img.get_rect(center=(SCREEN_W // 2, 60)))
        if w.time < w.diff.grace:
            self.text("Algo duerme en el laberinto... encuentra la luz verde.", self.f_small,
                      (150, 150, 160), (SCREEN_W // 2, SCREEN_H - 94), True)
        if w.time < w.monster.incapacitated_until:
            remaining = math.ceil(w.monster.incapacitated_until - w.time)
            self.text(f"Monstruo incapacitado: {remaining} s", self.f_small,
                      (150, 190, 230), (SCREEN_W // 2, SCREEN_H - 116), True)

    def draw_inventory(self):
        slot_size, gap, padding = 44, 3, 6
        width = 5 * slot_size + 4 * gap
        height = slot_size + padding * 2
        left = (SCREEN_W - width) // 2
        top = SCREEN_H - height - 20
        panel = pygame.Rect(left - padding, top - padding, width + padding * 2,
                            height + padding * 2)
        pygame.draw.rect(self.screen, (8, 9, 12), panel)
        pygame.draw.rect(self.screen, (88, 90, 94), panel, 1)

        for index in range(5):
            x = left + index * (slot_size + gap)
            rect = pygame.Rect(x, top, slot_size, slot_size)
            selected = index == self.selected_slot
            pygame.draw.rect(self.screen, (67, 63, 53) if selected else (28, 29, 32), rect)
            pygame.draw.rect(self.screen, (220, 194, 130) if selected else (86, 88, 92), rect, 2)
            self.text(str(index + 1), self.f_small, (185, 185, 185),
                      (x + 3, top + 1), shadow=False)

            if index == 0:
                icon = pygame.transform.scale(self.renderer.pebble_sprite, (27, 27))
                self.screen.blit(icon, icon.get_rect(center=(rect.centerx, rect.centery + 2)))
                count = self.world.pebbles
            elif index == 1:
                icon = pygame.transform.scale(self.renderer.weapon_sprite, (32, 22))
                icon.set_alpha(255 if self.world.ammo else 95)
                self.screen.blit(icon, icon.get_rect(center=(rect.centerx, rect.centery + 2)))
                count = f"{self.world.ammo}/{MAGAZINE_SIZE}"
            else:
                count = None

            if count is not None:
                label = self.f_small.render(str(count), True, (240, 240, 230))
                self.screen.blit(label, label.get_rect(bottomright=(rect.right - 3,
                                                                     rect.bottom - 2)))

        reserve = self.f_small.render(f"R RECARGA {self.world.ammo_reserve}",
                          True, (180, 180, 185))
        self.screen.blit(reserve, (panel.right + 10, panel.centery - reserve.get_height() // 2))

    def draw_end(self):
        w = self.world
        if w.state == LOST:
            if w.end_time < 0.72:
                self.screen.blit(self.jumpscare_image, (0, 0))
                rng = random.Random(int(w.end_time * 36))
                for _ in range(7):
                    y = rng.randrange(SCREEN_H)
                    height = rng.randrange(2, 10)
                    offset = rng.randrange(-24, 25)
                    self.screen.blit(self.jumpscare_image, (offset, y),
                                     (0, y, SCREEN_W, height))
                if rng.random() < 0.28:
                    pygame.draw.rect(self.screen, (9, 10, 13),
                                     (0, rng.randrange(SCREEN_H), SCREEN_W, 2))
            else:
                fade = min(255, int((w.end_time - 0.72) / 0.9 * 255))
                veil = pygame.Surface((SCREEN_W, SCREEN_H))
                veil.fill((0, 0, 0))
                veil.set_alpha(fade)
                self.screen.blit(veil, (0, 0))
            if w.end_time > 1.6:
                self.text("Te encontró.", self.f_big, (190, 40, 40), (SCREEN_W // 2, 180), True)
        else:
            veil = pygame.Surface((SCREEN_W, SCREEN_H))
            veil.fill((0, 10, 4))
            veil.set_alpha(min(200, int(w.end_time / 1.2 * 200)))
            self.screen.blit(veil, (0, 0))
            if w.end_time > 1.0:
                self.text("Escapaste.", self.f_big, (110, 230, 140), (SCREEN_W // 2, 180), True)
        if w.end_time > 1.6:
            mm, ss = divmod(int(w.time), 60)
            lines = [f"Tiempo: {mm:02d}:{ss:02d}   ·   Ruidos hechos: {w.noises_made}   ·   "
                     f"Veces que te oyó: {w.monster.heard_count}",
                     f"IA: {w.diff.algorithm.upper()}   ·   Nodos expandidos: {w.monster.total_expanded}   ·   "
                     f"Semilla: {w.seed}",
                     "Enter: jugar otra vez    M: menú    F1: modo dev (ver lo que pensaba la IA)"]
            for i, l in enumerate(lines):
                self.text(l, self.f_small, (180, 180, 190), (SCREEN_W // 2, 290 + i * 34), True)

    def draw_play(self):
        self._sync_window()
        self.renderer.render(self.view, self.world, self.selected_slot)
        game_area = self.screen.subsurface((0, 0, SCREEN_W, SCREEN_H))
        pygame.transform.scale(self.view, (SCREEN_W, SCREEN_H), game_area)
        if self.scene != END:
            if self.show_map and self.world.diff.minimap != "off":
                self.draw_minimap()
            self.draw_hud()
        if self.scene == PAUSE:
            veil = pygame.Surface((SCREEN_W, SCREEN_H))
            veil.set_alpha(150)
            self.screen.blit(veil, (0, 0))
            self.text("Pausa", self.f_big, (230, 230, 235), (SCREEN_W // 2, 200), True)
            self.text("Esc: seguir    M: menú", self.f, (170, 170, 180), (SCREEN_W // 2, 280), True)
        if self.scene == END:
            self.draw_end()
        if self.dev:
            self.devview.draw(self.screen, self.world, self.f, self.f_dev)

    def draw_dev_checkbox(self):
        r = self.dev_box
        hot = self.scene != PLAY and r.inflate(110, 8).collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, (10, 10, 14), r.inflate(6, 6), border_radius=3)
        pygame.draw.rect(self.screen, (255, 120, 120) if hot or self.dev else (140, 140, 150), r, 2,
                         border_radius=3)
        if self.dev:
            pygame.draw.line(self.screen, (255, 90, 90), (r.x + 4, r.centery), (r.x + 8, r.bottom - 5), 3)
            pygame.draw.line(self.screen, (255, 90, 90), (r.x + 8, r.bottom - 5), (r.right - 4, r.y + 4), 3)
        label = "Modo dev" + (" (F1)" if self.scene == PLAY else "")
        self.text(label, self.f_small, (235, 235, 240) if self.dev else (160, 160, 170),
                  (r.right + 8, r.y + 1))

    # ---------------------------------------------------------- bucle
    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle(e)
            if self.scene == LOADING:
                self.draw_loading(dt)
                if self._generation_future is not None and self._generation_future.done():
                    self._finish_generation()
            elif self.scene == MENU:
                self.draw_menu()
            else:
                self.update_play(dt)
                self.draw_play()
            if self.scene != LOADING:
                self.draw_dev_checkbox()
            pygame.display.flip()
        self._generation_executor.shutdown(wait=True, cancel_futures=True)
        pygame.quit()
