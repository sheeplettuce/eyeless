"""Pruebas rápidas sin ventana:  python -m unittest discover tests"""
import os
import math
import random
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.config import (DIFFICULTIES, PROXIMA_DOS_MOVE_RANGE, SCREEN_W,
                         STEP_HEAR_RANGE)
from game.maze import generate
from game.monster import INVESTIGATE, SEARCH
from game.pathfinding import bfs, dfs, astar
from game.world import World, PLAYING


class Tests(unittest.TestCase):
    def test_maze_connected(self):
        m = generate(10, 0.3, random.Random(1))
        self.assertEqual(len(m.bfs_dist((1, 1))), len(m.floor))
        self.assertEqual(len(m.doors), 5)
        self.assertEqual(len(m.rooms), 5)
        self.assertGreater(len({len(room) for room in m.rooms}), 1)

    def test_puertas_abren_salones_y_evitan_atrapar_al_jugador(self):
        world = World(DIFFICULTIES[1], seed=31)
        door = next(iter(world.maze.doors))
        entrance = next(tile for tile in ((door[0] + dx, door[1] + dy)
                                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                        if tile in world.maze.floor)

        def face(from_tile, to_tile):
            world.px, world.py = from_tile[0] + 0.5, from_tile[1] + 0.5
            world.player_tile = from_tile
            world.angle = math.atan2(to_tile[1] - from_tile[1], to_tile[0] - from_tile[0])

        face(entrance, door)
        self.assertTrue(world.interact_door())
        room_tile = next(tile for tile in world.maze.room_tiles
                         if abs(tile[0] - door[0]) + abs(tile[1] - door[1]) == 1)
        self.assertIn(room_tile, world.maze.floor)

        world.px, world.py = door[0] + 0.5, door[1] + 0.5
        world.player_tile = door
        world.angle = 0.0
        self.assertFalse(world.interact_door())
        self.assertTrue(world.maze.doors[door])
        self.assertIn(door, world.maze.adj)

        face(room_tile, door)
        self.assertFalse(world.interact_door())
        self.assertTrue(world.maze.doors[door])

        corridor = next(tile for tile in world.maze.adj[door]
                        if tile != room_tile and tile in world.maze.floor)
        world.px, world.py = door[0] + 0.05, door[1] + 0.5
        world.player_tile = corridor
        world.angle = math.atan2(corridor[1] - door[1], corridor[0] - door[0])
        self.assertFalse(world.interact_door())
        self.assertTrue(world.maze.doors[door])

        face(entrance, door)
        self.assertTrue(world.interact_door())
        self.assertNotIn(room_tile, world.maze.floor)

    def test_paths_valid_and_optimal(self):
        rng = random.Random(2)
        m = generate(10, 0.3, rng)
        for _ in range(50):
            a, b = rng.sample(m.floor, 2)
            rb, ra, rd = bfs(m, a, b), astar(m, a, b), dfs(m, a, b, rng, greedy=False)
            self.assertEqual(rb.cost, ra.cost)
            self.assertGreaterEqual(rd.cost, rb.cost)
            for r in (rb, ra, rd):
                self.assertEqual((r.path[0], r.path[-1]), (a, b))
                for p, q in zip(r.path, r.path[1:]):
                    self.assertIn(q, m.adj[p])

    def test_world_runs(self):
        for d in DIFFICULTIES:
            w = World(d, seed=3)
            for _ in range(600):
                w.update(0.05)
                if w.state != PLAYING:
                    break

    def test_sombras_perlin_deterministas(self):
        first = World(DIFFICULTIES[1], seed=27).floor_darkness
        second = World(DIFFICULTIES[1], seed=27).floor_darkness
        self.assertEqual(first, second)
        self.assertGreater(max(first.values()), 0.1)
        self.assertLessEqual(max(first.values()), 0.48)
        self.assertGreater(len(set(first.values())), 1)

    def test_ruido_interrumpe_busqueda_activa(self):
        w = World(DIFFICULTIES[1], seed=8)
        monster = w.monster
        monster.deaf_until = 0.0
        monster.diff = replace(monster.diff, hear_error=0)
        monster.state = SEARCH
        monster.search_left = 0.1
        monster.idle = 0.8
        origin = monster.here
        next_tile = w.maze.adj[origin][0]
        monster.cur, monster.nxt, monster.t = origin, next_tile, 0.35
        monster.goal = w.maze.adj[next_tile][0]
        monster.path = [monster.goal]
        target = origin
        previous_replans = monster.replans

        with patch.object(monster.rng, "random", return_value=0.0):
            heard = monster.hear(target, 3, w.time)

        self.assertTrue(heard)
        self.assertEqual(monster.state, INVESTIGATE)
        self.assertEqual(monster.goal, target)
        self.assertEqual(monster.idle, 0.0)
        self.assertEqual(monster.search_left, monster.diff.search_time)
        self.assertEqual(monster.replans, previous_replans + 1)
        self.assertEqual((monster.cur, monster.nxt), (next_tile, origin))
        self.assertAlmostEqual(monster.t, 0.65)

    def test_ruido_fija_y_actualiza_posicion_exacta_por_cinco_segundos(self):
        w = World(DIFFICULTIES[1], seed=13)
        monster = w.monster
        monster.deaf_until = 0.0
        monster.idle = 10.0
        player_tile = sorted(t for t, d in w.maze.bfs_dist(monster.here).items() if d == 5)[0]
        w.player_tile = player_tile
        w.emit_noise(player_tile, 30, "paso")

        self.assertEqual(monster.goal, player_tile)
        self.assertEqual(monster.focus_target, player_tile)
        self.assertAlmostEqual(monster.focus_until, w.time + 5.0)
        moved_tile = w.maze.adj[player_tile][0]
        monster.update(0.1, 0.1, moved_tile)
        self.assertEqual(monster.goal, moved_tile)
        self.assertEqual(monster.focus_target, moved_tile)
        monster.update(0.1, 5.1, moved_tile)
        self.assertIsNone(monster.focus_target)
        self.assertNotEqual(monster.state, INVESTIGATE)

    def test_oido_alcanza_el_radio_y_sprint_gasta_resistencia(self):
        w = World(DIFFICULTIES[1], seed=14)
        monster = w.monster
        monster.deaf_until = 0.0
        far_tile = sorted(t for t, d in w.maze.bfs_dist(monster.here).items()
                          if d == w.diff.hear_radius)[0]
        self.assertTrue(monster.hear(far_tile, w.diff.hear_radius, 0.0))

        neighbor = w.maze.adj[w.start][0]
        w.px, w.py = w.start[0] + 0.5, w.start[1] + 0.5
        before = (w.px, w.py)
        w.move_player(neighbor[0] - w.start[0], neighbor[1] - w.start[1], True, 0.1)
        self.assertTrue(w.sprinting)
        self.assertLess(w.stamina, 100.0)
        self.assertGreater(math.dist(before, (w.px, w.py)), 0.2)
        spent = w.stamina
        w.move_player(1, 0, False, 0.5)
        self.assertGreater(w.stamina, spent)

    def test_sprint_supera_al_monstruo_en_todas_las_dificultades(self):
        for diff in DIFFICULTIES:
            with self.subTest(dificultad=diff.key):
                w = World(diff, seed=25)
                neighbor = w.maze.adj[w.start][0]
                direction = (neighbor[0] - w.start[0], neighbor[1] - w.start[1])
                before = (w.px, w.py)
                w.move_player(*direction, True, 0.05)
                speed = math.dist(before, (w.px, w.py)) / 0.05
                self.assertGreater(speed, diff.monster_speed)

    def test_piedras_y_armas_se_recogen_y_desaparecen(self):
        w = World(DIFFICULTIES[1], seed=26)
        self.assertEqual(len(w.weapon_pickups), 2)
        self.assertEqual((w.ammo, w.ammo_reserve), (3, 3))
        self.assertTrue(all(room & (w.stone_pickups | w.weapon_pickups)
                            for room in w.maze.rooms))
        self.assertTrue(w.reload_weapon())
        self.assertEqual((w.ammo, w.ammo_reserve), (6, 0))
        self.assertFalse(w.reload_weapon())

        stone = next(iter(w.stone_pickups))
        stones_before = w.pebbles
        w.px, w.py = stone[0] + 0.5, stone[1] + 0.5
        w.update(0.01)
        self.assertEqual(w.pebbles, stones_before + 1)
        self.assertNotIn(stone, w.stone_pickups)

        weapon = next(iter(w.weapon_pickups))
        reserve_before = w.ammo_reserve
        w.px, w.py = weapon[0] + 0.5, weapon[1] + 0.5
        w.update(0.01)
        self.assertEqual(w.ammo_reserve, reserve_before + 6)
        self.assertNotIn(weapon, w.weapon_pickups)

    def test_arma_incapacita_sin_matar_segun_dificultad(self):
        expected = {"facil": 60.0, "medio": 40.0, "dificil": 25.0}
        for diff in DIFFICULTIES:
            with self.subTest(dificultad=diff.key):
                w = World(diff, seed=27)
                w.monster.deaf_until = 0.0
                w.monster.idle = 0.0
                neighbor = w.maze.adj[w.start][0]
                w.monster.cur, w.monster.nxt = w.start, neighbor
                w.monster.t = 0.25
                w.px, w.py = w.start[0] + 0.5, w.start[1] + 0.5
                w.player_tile = w.start
                w.angle = math.atan2(neighbor[1] - w.start[1],
                                     neighbor[0] - w.start[0])
                w.ammo = 1
                monster_pos = w.monster.pos
                self.assertGreater(w.monster.current_speed(), 0.0)

                self.assertTrue(w.shoot_weapon())
                self.assertEqual(w.ammo, 0)
                self.assertEqual(w.monster.incapacitated_until, expected[diff.key])
                self.assertEqual(w.noise_log[-1].kind, "disparo")
                self.assertTrue(any(event[0] == "gunshot" for event in w.events))
                self.assertTrue(any(event[0] == "monster_hit" for event in w.events))
                self.assertTrue(w._monster_incapacitation_active)
                w.update(0.1)
                self.assertEqual(w.monster.pos, monster_pos)
                self.assertEqual(w.state, PLAYING)
                w.monster.update(0.1, expected[diff.key] - 0.1, w.player_tile)
                self.assertEqual(w.monster.pos, monster_pos)
                w.monster.update(0.1, expected[diff.key] + 0.1, w.player_tile)
                self.assertNotEqual(w.monster.pos, monster_pos)

    def test_disparo_fallido_no_genera_sollozo(self):
        w = World(DIFFICULTIES[1], seed=27)
        w.monster.idle = 1000.0
        w.angle = math.pi
        w.ammo = 1
        self.assertTrue(w.shoot_weapon())
        self.assertTrue(any(event[0] == "gunshot" for event in w.events))
        self.assertFalse(any(event[0] == "monster_hit" for event in w.events))

    def test_paneo_estereo_distingue_frente_espalda_e_lados(self):
        w = World(DIFFICULTIES[1], seed=16)
        front = w._bearing_pan(w.px + math.cos(w.angle), w.py + math.sin(w.angle))
        back = w._bearing_pan(w.px - math.cos(w.angle), w.py - math.sin(w.angle))
        right = w._bearing_pan(w.px - math.sin(w.angle), w.py + math.cos(w.angle))
        left = w._bearing_pan(w.px + math.sin(w.angle), w.py - math.cos(w.angle))
        self.assertAlmostEqual(front[0], 0.0, places=5)
        self.assertGreater(front[1], 0.99)
        self.assertAlmostEqual(back[0], 0.0, places=5)
        self.assertLess(back[1], -0.99)
        self.assertGreater(right[0], 0.99)
        self.assertAlmostEqual(right[1], 0.0, places=5)
        self.assertLess(left[0], -0.99)

    def test_respiracion_del_jugador_y_piedra_visible_hasta_caer(self):
        w = World(DIFFICULTIES[1], seed=17)
        w.sprinting = True
        w.update(0.5)
        self.assertTrue(any(event[0] == "player_breath" for event in w.events))
        w.events.clear()

        self.assertTrue(w.throw_pebble())
        self.assertEqual(len(w.pebble_projectiles), 1)
        projectile = w.pebble_projectiles[0]
        self.assertFalse(projectile["landed"])
        w._update_pebbles(projectile["duration"])
        self.assertTrue(projectile["landed"])
        self.assertTrue(any(event[0] == "pebble" for event in w.events))
        self.assertEqual(w.noise_log[-1].kind, "piedra")
        self.assertFalse(w.monster.track_player)

    def test_grito_es_mas_lejano_que_un_paso_y_da_la_posicion_exacta(self):
        w = World(DIFFICULTIES[1], seed=19)
        with patch.object(w.monster, "hear", return_value=True) as hear:
            self.assertTrue(w.shout())
        radius = w.noise_log[-1].radius
        self.assertEqual(w.noise_log[-1].kind, "grito")
        self.assertGreater(radius, round(w.diff.hear_radius * 1.3))
        hear.assert_called_once_with(w.player_tile, radius, w.time,
                                     exact_target=w.player_tile)
        self.assertEqual(w.events[-1][0], "shout")

    def test_hint_de_salida_indica_distancia_y_direccion(self):
        w = World(DIFFICULTIES[1], seed=20)
        next_tile = min(w.maze.adj[w.player_tile],
                        key=w.exit_distances.__getitem__)
        w.angle = math.atan2(next_tile[1] - w.player_tile[1],
                             next_tile[0] - w.player_tile[0])
        self.assertEqual(w.exit_hint(),
                         f"Salida: {w.exit_distances[w.player_tile]} pasos, al frente")
        w.player_tile = w.exit
        self.assertEqual(w.exit_hint(), "¡La salida está aquí!")

    def test_respiracion_y_banco_de_sonidos(self):
        import pygame
        from game.audio import Audio, HEY_VOICES, MONSTER_VOICES, SOUND_BANK
        self.assertIn("grunido", MONSTER_VOICES)
        pygame.init()
        pygame.mixer.init(22050, -16, 2, 512, allowedchanges=0)
        audio = Audio()
        self.assertEqual(pygame.mixer.get_init(), (22050, -16, 2))
        self.assertAlmostEqual(audio.sounds["breath"].get_length(), 1.25, places=2)
        self.assertAlmostEqual(audio.sounds["player_breath"].get_length(), 1.0, places=2)
        self.assertAlmostEqual(audio.sounds["creak"].get_length(), 0.3, places=2)
        for name in ("breath", "player_breath", "gunshot", *SOUND_BANK):
            self.assertIn(name, audio.sounds)
            self.assertGreater(len(audio.sounds[name].get_raw()), 0)
        self.assertGreater(audio._pan_gains(-1.0, 0.0)[0],
                           audio._pan_gains(-1.0, 0.0)[1])
        self.assertGreater(audio._pan_gains(1.0, 0.0)[1],
                           audio._pan_gains(1.0, 0.0)[0])
        audio.handle(("player_breath", 0.8, 0.0, 1.0))
        audio.handle(("monster_breath", 0.8, 0.0, 1.0))
        with patch.object(audio, "_play") as play:
            audio.handle(("step", 0.0, 0.0, 1.0))
            play.assert_called_once_with("step2", 0.19, 0.0, front=1.0)
        with patch("game.audio.random.choice", side_effect=lambda choices: choices[0]):
            with patch.object(audio, "_play") as play:
                audio.handle(("monster_voice", 0.4, 1.0, 0.0))
                audio.handle(("monster_near", 1.0, 0.0))
                audio.handle(("shout", 1.0, 0.0, 1.0))
                audio.handle(("jumpscare", 1.0, 0.0))
        self.assertEqual([call.args[0] for call in play.call_args_list],
                         [MONSTER_VOICES[0], "proxima_dos_move",
                          HEY_VOICES[0], "scream"])
        self.assertTrue(pygame.mixer.get_busy())
        audio.stop()

    def test_sobbing_bloquea_todos_los_sonidos_hasta_recuperacion(self):
        import pygame
        from game.audio import Audio

        class ShotChannel:
            busy = True

            def get_busy(self):
                return self.busy

        pygame.init()
        pygame.mixer.init(22050, -16, 2, 512, allowedchanges=0)
        audio = Audio()
        shot_channel = ShotChannel()
        with patch.object(pygame.mixer, "stop") as stop_audio:
            with patch.object(audio, "_play", return_value=shot_channel) as play:
                audio.handle(("monster_hit", 0.0, 1.0))
                audio.handle(("gunshot", 1.0, 0.0, 1.0))
                audio.handle(("monster_voice", 0.4, 1.0, 0.0))
                audio.handle(("shout", 1.0, 0.0, 1.0))
                play.assert_called_once_with("gunshot", 1.0, 0.0, front=1.0)
                self.assertTrue(audio._exclusive_sobbing)
                self.assertIsNotNone(audio._pending_sobbing)
                shot_channel.busy = False
                audio.handle(("monster_voice", 0.4, 1.0, 0.0))
                self.assertEqual(play.call_args_list[-1].args[0], "sobbing")
                self.assertEqual(play.call_args_list[-1].kwargs,
                                 {"loops": -1, "front": 1.0})
                audio.handle(("monster_recovered",))
                self.assertFalse(audio._exclusive_sobbing)
        self.assertEqual(stop_audio.call_count, 2)
        self.assertEqual(play.call_args.args[0], "drone")
        audio.stop()

    def test_sobbing_se_detiene_cuando_el_monstruo_se_recupera(self):
        world = World(DIFFICULTIES[2], seed=27)
        world.monster.incapacitated_until = world.time + 0.1
        world._monster_incapacitation_active = True
        world.update(0.06)
        self.assertFalse(any(event[0] == "monster_recovered" for event in world.events))
        world.update(0.06)
        self.assertEqual(sum(event[0] == "monster_recovered" for event in world.events), 1)
        world.update(0.06)
        self.assertEqual(sum(event[0] == "monster_recovered" for event in world.events), 1)

    def test_jumpscare_al_perder_y_scream_solo_al_perder(self):
        import types
        import pygame
        from unittest.mock import patch
        from game.app import App, END

        app = App(types.SimpleNamespace(dificultad="facil", semilla=9,
                                        debug=False, silencio=True))
        app.world.state = "lost"
        with patch.object(app.audio, "handle") as play_sound:
            app.update_play(0.01)
        self.assertEqual(app.scene, END)
        self.assertTrue(app._jumpscare_played)
        play_sound.assert_called_once_with(("jumpscare", 1.0, 0.0))

        app.world.end_time = 0.3
        app.screen.fill((0, 0, 0))
        app.draw_end()
        self.assertEqual(app.jumpscare_image.get_size(), (SCREEN_W, 540))
        self.assertEqual(app.screen.get_at((0, 0)), app.jumpscare_image.get_at((0, 0)))

    def test_menu_oscuro_muestra_menusito_a_la_derecha(self):
        import types
        from game.app import App

        app = App(types.SimpleNamespace(dificultad=None, semilla=None,
                                        debug=False, silencio=True))
        app.draw_menu()
        self.assertEqual(app.screen.get_at((0, 0))[:3], (0, 0, 0))
        image_rect = app.menu_image.get_rect(topright=(SCREEN_W - 38, 40))
        self.assertGreater(image_rect.left, SCREEN_W // 2)
        self.assertEqual(image_rect.right, SCREEN_W - 38)
        self.assertGreater(max(app.menu_image.get_at((180, 180))[:3]), 0)

    def test_monster_voice_sounds_even_beyond_step_hearing_range(self):
        w = World(DIFFICULTIES[2], seed=21)
        distances = w.maze.bfs_dist(w.player_tile)
        far_tile = max(distances, key=distances.__getitem__)
        self.assertGreater(distances[far_tile], STEP_HEAR_RANGE)
        w.monster.cur = w.monster.nxt = far_tile
        w.monster.t = 0.0
        w.monster.idle = 1000.0
        w._voice_timer = 0.0
        w.update(0.05)
        voice = next(event for event in w.events if event[0] == "monster_voice")
        self.assertGreaterEqual(voice[1], 0.24)
        self.assertLessEqual(voice[1], 0.64)
        self.assertTrue(-1.0 <= voice[2] <= 1.0)
        self.assertTrue(-1.0 <= voice[3] <= 1.0)

    def test_frase_periodica_tambien_suena_cerca_y_fuera_de_patrulla(self):
        w = World(DIFFICULTIES[2], seed=21)
        distances = w.maze.bfs_dist(w.player_tile)
        near_tile = next(tile for tile, distance in distances.items() if distance == 1)
        w.monster.cur = w.monster.nxt = near_tile
        w.monster.t = 0.0
        w.monster.idle = 1000.0
        w.monster.state = "INVESTIGA"
        w._voice_timer = 0.0
        w.update(0.05)
        self.assertTrue(any(event[0] == "monster_voice" for event in w.events))
        self.assertTrue(any(event[0] == "monster_near" for event in w.events))

    def test_proxima_dos_move_solo_suena_a_diez_pasos_o_menos(self):
        w = World(DIFFICULTIES[2], seed=21)
        distances = w.maze.bfs_dist(w.player_tile)
        near_tile = next(tile for tile, distance in distances.items()
                         if distance == PROXIMA_DOS_MOVE_RANGE)
        w.monster.cur = w.monster.nxt = near_tile
        w.monster.t = 0.0
        w.monster.idle = 1000.0
        w._voice_timer = 0.0
        w.update(0.05)
        self.assertTrue(any(event[0] == "monster_near" for event in w.events))
        self.assertTrue(any(event[0] == "monster_voice" for event in w.events))

        far_tile = next(tile for tile, distance in distances.items()
                        if distance == PROXIMA_DOS_MOVE_RANGE + 1)
        w.monster.cur = w.monster.nxt = far_tile
        w.monster.idle = 1000.0
        w._voice_timer = 0.0
        w.events.clear()
        w.update(0.05)
        self.assertFalse(any(event[0] == "monster_near" for event in w.events))

    def test_audio_panea_sin_construir_buffers_por_direccion(self):
        import pygame
        from game.audio import Audio
        pygame.init()
        pygame.mixer.init(22050, -16, 2, 512, allowedchanges=0)
        audio = Audio()
        front = audio._pan_gains(0.0, 1.0)
        rear = audio._pan_gains(0.0, -1.0)
        self.assertGreater(front[0], rear[0])
        self.assertGreater(front[1], rear[1])
        audio.handle(("step", 0.8, -1.0, 0.0))
        audio.stop()

    def test_puntos_azules_aparecen_y_se_reponen(self):
        for diff in DIFFICULTIES:
            w = World(diff, seed=18)
            initial = len(w.blue_points)
            self.assertEqual(initial, {"facil": 2, "medio": 3, "dificil": 4}[diff.key])
            self.assertTrue(w.blue_points.isdisjoint(w.noisy))
            w.monster.deaf_until = 1000.0
            w.update(120.0)
            self.assertGreater(len(w.blue_points), initial)

    def test_render_frame(self):
        import pygame
        from game.config import RENDER_W, RENDER_H
        from game.render import Renderer
        pygame.init()
        pygame.display.set_mode((RENDER_W, RENDER_H))
        w = World(DIFFICULTIES[1], seed=4)
        renderer = Renderer(w.maze)
        self.assertEqual(renderer.monster_sprites[0].get_size(), (64, 128))
        self.assertEqual(renderer.monster_sprites[0].get_at((32, 10)), (6, 5, 7, 255))
        self.assertNotEqual(pygame.image.tostring(renderer.monster_sprites[0], "RGBA"),
                            pygame.image.tostring(renderer.monster_sprites[1], "RGBA"))
        self.assertTrue(w.throw_pebble())
        w.pebble_projectiles[0]["elapsed"] = w.pebble_projectiles[0]["duration"] * 0.4
        renderer.render(pygame.Surface((RENDER_W, RENDER_H)), w)
        self.assertGreater(len(renderer._wall_column_cache), 0)
        self.assertLessEqual(len(renderer._wall_column_cache),
                             renderer._wall_column_cache_limit)

    # ---------------------------------------------------------------- novedades
    def _near_monster(self, w, steps):
        dm = w.maze.bfs_dist(w.monster.here)
        t = sorted(t for t, d in dm.items() if d == steps)[0]
        w.px, w.py, w.player_tile = t[0] + .5, t[1] + .5, t
        return t

    def test_pasos_se_oyen_varias_veces_por_tile(self):
        w = World(DIFFICULTIES[1], seed=3)
        w.monster.deaf_until, w.time = 0.0, 30.0
        self._near_monster(w, 5)
        w.monster.idle = 0.0
        w.monster._new_patrol()
        steps = 0
        for _ in range(120):                       # 6 s
            w.update(0.05)
            steps += sum(1 for e in w.events if e[0] == "step")
            w.events.clear()
            if w.state != PLAYING:
                break
        self.assertGreaterEqual(steps, 3)

    def test_niebla_sube_cerca_y_baja_lejos(self):
        w = World(DIFFICULTIES[2], seed=5)
        w.monster.deaf_until, w.time = 0.0, 30.0
        w.monster.idle = 999.0                     # quieto, para medir solo la niebla
        self._near_monster(w, 3)
        for _ in range(80):
            w.update(0.05)
        self.assertGreater(w.fog, 0.4)
        self._near_monster(w, 14)
        for _ in range(120):
            w.update(0.05)
        self.assertLess(w.fog, 0.05)

    def test_efectos_sonoros_aparecen_cerca_del_monstruo(self):
        w = World(DIFFICULTIES[1], seed=6)
        w.monster.deaf_until, w.time = 0.0, 30.0
        w.monster.idle = 999.0
        tile = sorted(t for t, d in w.maze.bfs_dist(w.monster.here).items() if d == 3)[0]
        w.px, w.py, w.player_tile = tile[0] + 0.5, tile[1] + 0.5, tile
        w._fx_timer = 0.0

        w.update(0.05)

        self.assertTrue(any(event[0] in ("monster_breath", "scrape") for event in w.events))
        self.assertFalse(any(event[0] == "monster_roar" for event in w.events))

    def test_traza_de_busqueda(self):
        rng = random.Random(9)
        m = generate(10, 0.3, rng)
        a, b = rng.sample(m.floor, 2)
        for fn in (bfs, astar):
            r = fn(m, a, b)
            self.assertEqual(len(r.order), r.expanded)
            self.assertEqual(r.order[0], a)
            self.assertIn(b, r.tree)
        w = World(DIFFICULTIES[2], seed=1)
        w.monster.deaf_until = 0.0
        w.monster._new_patrol()
        self.assertIsNotNone(w.monster.last_plan)
        self.assertEqual(w.monster.last_plan["algo"], "astar")

    def test_modo_dev_dibuja_y_casilla_funciona(self):
        import types
        import pygame
        from game.app import App
        app = App(types.SimpleNamespace(dificultad="dificil", semilla=2, debug=False, silencio=True))
        app.world.monster.deaf_until = 0.0
        app.world.monster._new_patrol()
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(0, 0)))
        self.assertEqual(app.world.noise_log[-1].kind, "grito")
        app.dev = True
        for _ in range(5):
            app.update_play(1 / 60)
            app.draw_play()
            app.draw_dev_checkbox()
        self.assertEqual(pygame.display.get_surface().get_size(), (SCREEN_W, 540))
        # en pausa el ratón está libre: un clic sobre la casilla la apaga
        app.scene = "pause"
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app.dev_box.center))
        self.assertFalse(app.dev)
        app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app.dev_box.center))
        self.assertTrue(app.dev)
        app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
        self.assertFalse(app.dev)
        self.assertEqual(pygame.display.get_surface().get_size(), (SCREEN_W, 540))

    def test_partida_larga_sin_errores(self):
        import types
        from game.app import App
        for d in ("facil", "medio", "dificil"):
            app = App(types.SimpleNamespace(dificultad=d, semilla=11, debug=True, silencio=True))
            app.world.monster.deaf_until = 0.0
            for i in range(480):                    # ~8 s simulados
                if i % 120 == 0:
                    app.world.emit_noise(app.world.player_tile, app.world.diff.hear_radius, "paso")
                app.update_play(1 / 60)
                app.draw_play()
                if app.world.state != PLAYING:
                    break


if __name__ == "__main__":
    unittest.main()
