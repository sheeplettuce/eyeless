"""Efectos sintetizados y voces del banco de sonidos."""
import array
import math
import random
from pathlib import Path

import pygame

RATE = 22050


def _lowpass(samples, k=0.15):
    out, y = [], 0.0
    for s in samples:
        y += k * (s - y)
        out.append(y)
    return out


HEY_VOICES = ("hey_1", "hey_2", "hey_3")
MONSTER_VOICES = (
    "a_donde_vas",
    "escucho_tus_latidos",
    "estoy_detras_de_ti",
    "grunido",
    "no_tienes_mucho_tiempo",
    "puedo_olerte",
    "se_donde_te_encuentras",
    "te_estoy_escuchando",
    "ya_te_cansaste",
)
SOUND_BANK = (*HEY_VOICES, *MONSTER_VOICES, "grunido", "proxima_dos_move",
              "sobbing", "scream")


class Audio:
    def __init__(self, enabled=True):
        self.ok = False
        self.sounds = {}
        self._step_flip = False
        self._exclusive_sobbing = False
        self._pending_sobbing = None
        self._shot_channel = None
        self._hey_voices = HEY_VOICES
        self._monster_voices = MONSTER_VOICES
        if not enabled:
            return
        try:
            mixer_format = (RATE, -16, 2)
            if pygame.mixer.get_init() not in (None, mixer_format):
                pygame.mixer.quit()
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(RATE, -16, 2, 512, allowedchanges=0)
            pygame.mixer.set_num_channels(16)
            self._build()
            self.ok = True
        except (pygame.error, NotImplementedError):
            self.ok = False

    # ---------------------------------------------------------- síntesis
    @staticmethod
    def _make(samples):
        buf = array.array("h")
        for s in samples:
            v = int(max(-1.0, min(1.0, s)) * 32767)
            buf.append(v)
            buf.append(v)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _build(self):
        rng = random.Random(3)
        # crujido de madera: sierra grave + ruido filtrado
        n = int(RATE * 0.3)
        noise = _lowpass([rng.uniform(-1, 1) for _ in range(n)], 0.12)
        phase, creak = 0.0, []
        for i in range(n):
            t = i / RATE
            env = math.sin(math.pi * t / 0.3) ** 0.7
            f = 110 + 35 * math.sin(2 * math.pi * 3.1 * t) + 20 * math.sin(2 * math.pi * 11 * t)
            phase += f / RATE
            saw = (phase % 1.0) * 2 - 1
            creak.append((0.35 * saw + 2.2 * noise[i]) * env * 0.55)
        self.sounds["creak"] = self._make(creak)

        # pasos pesados del monstruo (dos variantes que se alternan).
        # Antes era un seno de ~60 Hz -> sub-grave que las bocinas/audífonos normales casi no
        # reproducen. Ahora: golpe grave con armónicos (tanh) + "bofetada" de ruido medio + arrastre.
        for name, base, seed in (("step", 74.0, 21), ("step2", 66.0, 22)):
            r2 = random.Random(seed)
            n = int(RATE * 0.42)
            slap = _lowpass([r2.uniform(-1, 1) for _ in range(n)], 0.42)
            scuff = _lowpass([r2.uniform(-1, 1) for _ in range(n)], 0.08)
            phase, buf = 0.0, []
            for i in range(n):
                t = i / RATE
                phase += (base + 95.0 * math.exp(-t * 20)) / RATE
                thump = math.sin(2 * math.pi * phase) * math.exp(-t * 11)
                x = 1.3 * thump + 3.0 * slap[i] * math.exp(-t * 42) \
                    + 2.4 * scuff[i] * math.exp(-((t - 0.11) / 0.05) ** 2) * 0.6
                buf.append(math.tanh(1.8 * x) * 0.95)
            self.sounds[name] = self._make(buf)

        # latido
        n = int(RATE * 0.8)
        hb = [0.0] * n
        for start, amp in ((0.0, 1.0), (0.27, 0.7)):
            s0 = int(start * RATE)
            for i in range(int(RATE * 0.22)):
                if s0 + i < n:
                    t = i / RATE
                    hb[s0 + i] += math.sin(2 * math.pi * 48 * t) * math.exp(-t * 22) * amp
        self.sounds["heart"] = self._make(hb)

        # exhalación áspera, con ruido filtrado y dos pulsos
        n = int(RATE * 1.25)
        breath_noise = _lowpass([rng.uniform(-1, 1) for _ in range(n)], 0.34)
        breath = []
        breath_phase = 0.0
        for i in range(n):
            t = i / RATE
            envelope = (math.sin(math.pi * t / 1.25) ** 1.5
                        * (0.55 + 0.45 * math.sin(2 * math.pi * 1.7 * t) ** 2))
            breath_phase += (76 + 9 * math.sin(2 * math.pi * 0.8 * t)) / RATE
            airflow = breath_noise[i] * 0.78 + math.sin(2 * math.pi * breath_phase) * 0.22
            breath.append(airflow * envelope * 0.82)
        self.sounds["breath"] = self._make(breath)

        player_noise = _lowpass([rng.uniform(-1, 1) for _ in range(RATE)], 0.32)
        player_breath = []
        for i, sample in enumerate(player_noise):
            t = i / RATE
            envelope = math.sin(math.pi * t) ** 0.85
            modulation = 0.7 + 0.3 * math.sin(2 * math.pi * 1.5 * t) ** 2
            air = sample * 0.78 + math.sin(2 * math.pi * 92 * t) * 0.22
            player_breath.append(air * envelope * modulation * 0.82)
        self.sounds["player_breath"] = self._make(player_breath)

        self.sounds["monster_breath"] = self.sounds["breath"]

        # gemido distante: armónicos que descienden con una capa de aire
        n = int(RATE * 1.8)
        groan_noise = _lowpass([rng.uniform(-1, 1) for _ in range(n)], 0.08)
        phase, groan = 0.0, []
        for i in range(n):
            t = i / RATE
            phase += (92 - 34 * t / 1.8 + 5 * math.sin(2 * math.pi * 1.1 * t)) / RATE
            envelope = math.sin(math.pi * t / 1.8) ** 1.2
            tone = math.sin(2 * math.pi * phase) + 0.35 * math.sin(4 * math.pi * phase)
            groan.append((0.42 * tone + 0.9 * groan_noise[i]) * envelope * 0.45)
        self.sounds["groan"] = self._make(groan)

        # roce de pasos y extremidades contra la pared
        n = int(RATE * 0.85)
        scrape_noise = _lowpass([rng.uniform(-1, 1) for _ in range(n)], 0.38)
        scrape = []
        for i in range(n):
            t = i / RATE
            envelope = math.sin(math.pi * t / 0.85) ** 0.8
            rasp = 0.65 + 0.35 * math.sin(2 * math.pi * 7.0 * t)
            scrape.append(scrape_noise[i] * envelope * rasp * 0.58)
        self.sounds["scrape"] = self._make(scrape)

        # piedra rebotando
        n = int(RATE * 0.35)
        pb = [0.0] * n
        for start, amp in ((0.0, 1.0), (0.11, 0.55), (0.19, 0.3)):
            s0 = int(start * RATE)
            for i in range(int(RATE * 0.12)):
                if s0 + i < n:
                    t = i / RATE
                    pb[s0 + i] += (rng.uniform(-1, 1) * 0.5 + math.sin(2 * math.pi * 2100 * t) * 0.5) \
                        * math.exp(-t * 45) * amp * 0.6
        self.sounds["pebble"] = self._make(pb)

        assets = Path(__file__).with_name("assets")
        self.sounds["gunshot"] = pygame.mixer.Sound(str(assets / "shoot_bitcrushed.wav"))

        # zumbido ambiente en bucle (ciclos enteros => sin cortes)
        secs = 4
        n = RATE * secs
        self.sounds["drone"] = self._make(
            [(math.sin(2 * math.pi * 55 * i / RATE) * 0.5 + math.sin(2 * math.pi * 58 * i / RATE) * 0.4
              + math.sin(2 * math.pi * 110 * i / RATE) * 0.15) * 0.22 for i in range(n)])

        sound_bank = assets / "SOUNDS"
        for name in SOUND_BANK:
            self.sounds[name] = pygame.mixer.Sound(str(sound_bank / f"{name.upper()}.wav"))

    # ---------------------------------------------------------- reproducción
    @staticmethod
    def _pan_gains(pan, front):
        angle = math.atan2(max(-1.0, min(1.0, pan)), max(-1.0, min(1.0, front)))
        side = math.sin(angle)
        rear = math.cos(angle) < 0
        rear_gain = 0.82 if rear else 1.0
        return (math.sqrt((1.0 - side) * 0.5) * rear_gain,
                math.sqrt((1.0 + side) * 0.5) * rear_gain)

    def _play(self, name, vol=1.0, pan=0.0, loops=0, front=1.0):
        if not self.ok or (self._exclusive_sobbing and name != "sobbing"):
            return
        spatial_names = ("step", "step2", "breath", "monster_breath",
                         "player_breath", "scrape", "pebble", "gunshot",
                         *self._hey_voices, *self._monster_voices,
                         "proxima_dos_move", "sobbing")
        ch = self.sounds[name].play(loops=loops)
        if ch:
            if name in spatial_names:
                left, right = self._pan_gains(pan, front)
            else:
                left = right = 1.0
            ch.set_volume(max(0.0, min(1.0, vol * left)),
                          max(0.0, min(1.0, vol * right)))
        return ch

    def _start_pending_sobbing(self):
        if self._pending_sobbing is None:
            return
        if self._shot_channel is not None and self._shot_channel.get_busy():
            return
        pan, front = self._pending_sobbing
        self._pending_sobbing = None
        self._shot_channel = None
        self._play("sobbing", 1.0, pan, loops=-1, front=front)

    def ambient(self):
        self._play("drone", 0.5, 0.0, loops=-1)

    def stop(self):
        if self.ok:
            pygame.mixer.stop()
        self._exclusive_sobbing = False
        self._pending_sobbing = None
        self._shot_channel = None

    def handle(self, ev):
        """ev = (tipo, a, b) generado por World.events."""
        if ev[0] == "monster_recovered":
            if self._exclusive_sobbing:
                if self.ok:
                    pygame.mixer.stop()
                self._exclusive_sobbing = False
                self._pending_sobbing = None
                self._shot_channel = None
                self.ambient()
            return
        if self._exclusive_sobbing:
            if self._pending_sobbing is not None and ev[0] == "gunshot":
                _, volume, pan, front = ev
                self._shot_channel = self._play("gunshot", volume, pan, front=front)
                self._start_pending_sobbing()
                return
            self._start_pending_sobbing()
            return
        if ev[0] == "monster_voice":
            _, volume, pan, front = ev
            self._play(random.choice(self._monster_voices), volume, pan, front=front)
            return
        if ev[0] == "monster_near":
            _, pan, front = ev
            self._play("proxima_dos_move", 1.0, pan, front=front)
            return
        if ev[0] == "monster_hit":
            _, pan, front = ev
            if self.ok:
                pygame.mixer.stop()
                self._exclusive_sobbing = True
                self._pending_sobbing = (pan, front)
            return
        kind, a, b, *direction = ev
        front = direction[0] if direction else 1.0
        if kind == "creak":
            self._play("creak", a)
        elif kind == "step":
            self._step_flip = not self._step_flip
            self._play("step2" if self._step_flip else "step", 0.19 + 0.68 * a, b,
                       front=front)
        elif kind == "heart":
            self._play("heart", 0.3 + 0.7 * a)
        elif kind == "pebble":
            self._play("pebble", 0.8, b, front=front)
        elif kind == "shout":
            self._play(random.choice(self._hey_voices), a, b, front=front)
        elif kind == "gunshot":
            self._play("gunshot", a, b, front=front)
        elif kind == "jumpscare":
            self._play("scream", a)
        elif kind in ("breath", "monster_breath", "player_breath",
                      "groan", "scrape"):
            if kind == "monster_breath":
                volume = 0.30 + 0.62 * a
            elif kind == "player_breath":
                volume = 0.38 + 0.55 * a
            else:
                base = {"breath": 0.20, "player_breath": 0.18, "groan": 0.24,
                        "scrape": 0.17}[kind]
                volume = base + 0.56 * a
            self._play(kind, volume, b, front=front)
