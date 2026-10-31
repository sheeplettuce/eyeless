"""Ruido de Perlin 2D (implementación propia, sin dependencias)."""
import math
import random

_GRADS = [(1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)]


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a, b, t):
    return a + t * (b - a)


class Perlin:
    def __init__(self, seed=0):
        rng = random.Random(seed)
        p = list(range(256))
        rng.shuffle(p)
        self.p = p * 2

    def noise(self, x, y):
        """Valor aproximado en [-1, 1]."""
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        xi &= 255
        yi &= 255
        u, v = _fade(xf), _fade(yf)
        p = self.p
        aa, ab = p[p[xi] + yi], p[p[xi] + yi + 1]
        ba, bb = p[p[xi + 1] + yi], p[p[xi + 1] + yi + 1]

        def g(h, dx, dy):
            gx, gy = _GRADS[h & 7]
            return gx * dx + gy * dy

        x1 = _lerp(g(aa, xf, yf), g(ba, xf - 1, yf), u)
        x2 = _lerp(g(ab, xf, yf - 1), g(bb, xf - 1, yf - 1), u)
        return _lerp(x1, x2, v)

    def octaves(self, x, y, n=3, persistence=0.5):
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(n):
            total += self.noise(x * freq, y * freq) * amp
            norm += amp
            amp *= persistence
            freq *= 2
        return total / norm
