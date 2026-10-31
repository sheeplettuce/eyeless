"""Distribución de tiles ruidosos usando ruido de Perlin."""
from .perlin import Perlin


def build_noise_tiles(maze, density, seed, exclude=()):
    """Devuelve {tile: intensidad 0.5..1.0}.

    Se escoge el `density` superior del campo de Perlin, así los tiles
    ruidosos salen en manchas (zonas de piso crujiente) y no uniformes.
    """
    perlin = Perlin(seed)
    vals = []
    for (x, y) in maze.floor:
        if (x, y) in exclude:
            continue
        v = (perlin.octaves(x * 0.32 + 0.37, y * 0.32 + 0.61, 3) + 1) / 2
        vals.append((v, (x, y)))
    vals.sort(reverse=True)
    chosen = vals[:max(1, int(len(vals) * density))]
    lo, hi = chosen[-1][0], chosen[0][0]
    return {t: 0.5 + 0.5 * (v - lo) / (hi - lo + 1e-9) for v, t in chosen}


def build_floor_darkness(maze, seed):
    """Genera manchas oscuras de suelo independientes de los tiles ruidosos."""
    perlin = Perlin(seed + 104729)
    darkness = {}
    for x, y in maze.floor:
        broad = (perlin.octaves(x * 0.16 + 4.1, y * 0.16 - 2.7, 3) + 1) / 2
        detail = (perlin.octaves(x * 0.39 - 7.3, y * 0.39 + 5.2, 2) + 1) / 2
        field = 0.72 * broad + 0.28 * detail
        darkness[(x, y)] = max(0.0, min(0.48, (field - 0.37) * 1.25))
    return darkness
