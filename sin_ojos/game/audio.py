"""Efectos sintetizados por código y voces pregrabadas con TTS."""
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


def _compress(samples, peak=0.85):
    source_peak = max((abs(sample) for sample in samples), default=0.0)
    if source_peak <= 1e-9:
        return samples
    return [math.tanh(sample / source_peak * 1.7) * peak for sample in samples]


def _monster_voice_effects(samples):
    if not samples:
        return []

    def pitch_shift(source, ratio):
        length = max(1, round(len(source) / ratio))
        return [
            source[min(int(i * ratio), len(source) - 1)]
            for i in range(length)
        ]

    pitched = pitch_shift(samples, 0.52)
    consonants = pitch_shift(samples, 0.78)
    original_low = _lowpass(samples, 0.045)
    original_hiss = [sample - low for sample, low in zip(samples, original_low)]
    consonant_low = _lowpass(consonants, 0.11)
    consonant_hiss = [sample - low for sample, low in zip(consonants, consonant_low)]
    hiss_env = _lowpass([abs(sample) for sample in original_hiss], 0.035)
    rng = random.Random(len(samples))
    air_noise = _lowpass([rng.uniform(-1.0, 1.0) for _ in consonants], 0.42)
    dark = _lowpass(pitched, 0.13)
    rumble = _lowpass(dark, 0.035)
    processed = []
    for i, sample in enumerate(pitched):
        t = i / RATE
        tremolo = 0.94 + 0.06 * math.sin(2 * math.pi * 3.2 * t)
        growl = rumble[i] * 0.18
        j = min(len(consonants) - 1, round(i * 0.52 / 0.78))
        air = min(1.0, hiss_env[min(len(hiss_env) - 1, round(i * 0.52))] * 8)
        whisper = (dark[i] * 0.68 + sample * 0.12 + growl
                   + consonant_hiss[j] * 1.35
                   + air_noise[j] * air * 0.075)
        processed.append(math.tanh(whisper * 1.65) * tremolo)
    echo_taps = ((0.16, 0.26), (0.32, 0.17), (0.51, 0.10))
    tail = round(echo_taps[-1][0] * RATE)
    output = [0.0] * (len(processed) + tail)
    for i, sample in enumerate(processed):
        output[i] += sample
        for delay, gain in echo_taps:
            output[i + round(delay * RATE)] += sample * gain
    return _compress(output, 0.86)


class Audio:
    def __init__(self, enabled=True):
        self.ok = False
        self.sounds = {}
        self._step_flip = False
        self._mono = {}
        self._directional = {}
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
        n = int(RATE * 0.6)
        noise = _lowpass([rng.uniform(-1, 1) for _ in range(n)], 0.12)
        phase, creak = 0.0, []
        for i in range(n):
            t = i / RATE
            env = math.sin(math.pi * t / 0.6) ** 0.7
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

        roar_noise = _lowpass([rng.uniform(-1, 1) for _ in range(int(RATE * 1.6))], 0.18)
        phase, roar = 0.0, []
        for i, sample in enumerate(roar_noise):
            t = i / RATE
            phase += (54 + 38 * math.sin(math.pi * t / 1.6)) / RATE
            envelope = math.sin(math.pi * t / 1.6) ** 0.65
            tone = math.sin(2 * math.pi * phase) + 0.4 * math.sin(4 * math.pi * phase)
            roar.append(math.tanh(1.7 * (tone + 1.4 * sample)) * envelope * 0.62)
        self.sounds["monster_roar"] = self._make(roar)
        self.sounds["monster_breath"] = self.sounds["breath"]

        glitch_rng = random.Random(731)
        n = int(RATE * 0.72)
        glitch = []
        for i in range(n):
            t = i / RATE
            gate = (1.0 if (t < 0.12 or 0.20 < t < 0.31
                            or 0.39 < t < 0.54 or 0.61 < t < 0.72) else 0.0)
            static = round(glitch_rng.uniform(-1.0, 1.0) * 18) / 18
            tone = math.sin(2 * math.pi * (390 + 1700 * t) * t)
            glitch.append(math.tanh((static * 0.82 + tone * 0.18) * gate * 2.4)
                          * (0.85 - 0.45 * t))
        self.sounds["jumpscare_glitch"] = self._make(glitch)

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

        n = int(RATE * 0.4)
        gunshot = []
        for i in range(n):
            t = i / RATE
            envelope = math.exp(-t * 32)
            crack = rng.uniform(-1.0, 1.0) * math.exp(-t * 90)
            thump = math.sin(2 * math.pi * 92 * t) * envelope
            gunshot.append(math.tanh(2.0 * crack + 0.8 * thump) * envelope * 0.9)
        self.sounds["gunshot"] = self._make(gunshot)

        # zumbido ambiente en bucle (ciclos enteros => sin cortes)
        secs = 4
        n = RATE * secs
        self.sounds["drone"] = self._make(
            [(math.sin(2 * math.pi * 55 * i / RATE) * 0.5 + math.sin(2 * math.pi * 58 * i / RATE) * 0.4
              + math.sin(2 * math.pi * 110 * i / RATE) * 0.15) * 0.22 for i in range(n)])

        assets = Path(__file__).with_name("assets")
        shout = pygame.mixer.Sound(str(assets / "shout_hey.wav"))
        shout_raw = array.array("h")
        shout_raw.frombytes(shout.get_raw())
        shout_samples = [sample / 32768.0 for sample in shout_raw[::2]]
        self.sounds["shout_hey"] = self._make(_compress(shout_samples, 0.92))
        for index in range(10):
            name = f"monster_voice_{index}"
            voice = pygame.mixer.Sound(str(assets / f"{name}.wav"))
            raw = array.array("h")
            raw.frombytes(voice.get_raw())
            source = [sample / 32768.0 for sample in raw[::2]]
            low = _lowpass(source, 0.22)
            breath_noise = _lowpass([rng.uniform(-1.0, 1.0) for _ in source], 0.18)
            envelope = _lowpass([abs(sample) for sample in source], 0.025)
            whisper = []
            for i, sample in enumerate(source):
                high = sample - low[i]
                whisper.append(0.38 * low[i] + 0.52 * high
                               + 0.12 * breath_noise[i] * min(1.0, envelope[i] * 7))
            self.sounds[name] = self._make(_monster_voice_effects(whisper))

        for name, sound in self.sounds.items():
            samples = array.array("h")
            samples.frombytes(sound.get_raw())
            self._mono[name] = samples[::2]

    # ---------------------------------------------------------- reproducción
    def _spatial_sound(self, name, pan, front):
        angle = math.atan2(max(-1.0, min(1.0, pan)), max(-1.0, min(1.0, front)))
        sector = round(angle / (2 * math.pi) * 16) % 16
        key = (name, sector)
        if key in self._directional:
            return self._directional[key]

        angle = sector / 16 * 2 * math.pi
        side = math.sin(angle)
        rear = math.cos(angle) < 0
        mono = self._mono[name]
        delay = int(abs(side) * RATE * 0.00055)
        delayed_ear = 0 if side > 0 else 1
        left_gain = math.sqrt((1.0 - side) * 0.5)
        right_gain = math.sqrt((1.0 + side) * 0.5)
        buf = array.array("h")
        filtered_samples = []
        filtered = 0.0
        for i, sample in enumerate(mono):
            filtered += (0.10 if rear else 0.32) * (sample - filtered)
            filtered_samples.append(filtered)
            source = filtered if rear else sample
            if i >= delay:
                delayed = filtered_samples[i - delay] if rear else mono[i - delay]
            else:
                delayed = source
            left = delayed if delayed_ear == 0 else source
            right = delayed if delayed_ear == 1 else source
            if rear:
                left, right = left * 0.82, right * 0.82
            buf.append(int(max(-32768, min(32767, left * left_gain))))
            buf.append(int(max(-32768, min(32767, right * right_gain))))
        sound = pygame.mixer.Sound(buffer=buf.tobytes())
        self._directional[key] = sound
        return sound

    def _play(self, name, vol=1.0, pan=0.0, loops=0, front=1.0):
        if not self.ok:
            return
        spatial_names = ("step", "step2", "breath", "monster_breath", "monster_roar",
                         "player_breath", "scrape", "pebble", "shout_hey",
                         "gunshot",
                         *(f"monster_voice_{index}" for index in range(10)))
        sound = self._spatial_sound(name, pan, front) if name in spatial_names else self.sounds[name]
        ch = sound.play(loops=loops)
        if ch:
            ch.set_volume(max(0.0, min(1.0, vol)))

    def ambient(self):
        self._play("drone", 0.5, 0.0, loops=-1)

    def stop(self):
        if self.ok:
            pygame.mixer.stop()

    def handle(self, ev):
        """ev = (tipo, a, b) generado por World.events."""
        if ev[0] == "monster_voice":
            _, index, volume, pan, front = ev
            self._play(f"monster_voice_{index}", volume, pan, front=front)
            return
        kind, a, b, *direction = ev
        front = direction[0] if direction else 1.0
        if kind == "creak":
            self._play("creak", a)
        elif kind == "step":
            self._step_flip = not self._step_flip
            self._play("step2" if self._step_flip else "step", 0.22 + 0.78 * a, b, front=front)
        elif kind == "heart":
            self._play("heart", 0.3 + 0.7 * a)
        elif kind == "pebble":
            self._play("pebble", 0.8, b, front=front)
        elif kind == "shout":
            self._play("shout_hey", a, b, front=front)
        elif kind == "gunshot":
            self._play("gunshot", a, b, front=front)
        elif kind == "jumpscare_glitch":
            self._play("jumpscare_glitch", a * 0.65)
        elif kind in ("breath", "monster_breath", "monster_roar", "player_breath",
                      "groan", "scrape"):
            if kind == "monster_breath":
                volume = 0.30 + 0.62 * a
            elif kind == "monster_roar":
                volume = 0.65 * a
            elif kind == "player_breath":
                volume = 0.38 + 0.55 * a
            else:
                base = {"breath": 0.20, "player_breath": 0.18, "groan": 0.24,
                        "scrape": 0.17}[kind]
                volume = base + 0.56 * a
            self._play(kind, volume, b, front=front)
