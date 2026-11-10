"""Constantes y configuración de dificultad."""
from dataclasses import dataclass

SCREEN_W, SCREEN_H = 960, 540      # ventana
RENDER_W, RENDER_H = 480, 270      # resolución interna del raycaster
FPS = 60
FOV = 0.66                         # longitud del plano de cámara (~66 grados)
LIGHT_DIST = 8.5                   # alcance de la linterna (en tiles)

WALK_SPEED = 2.6                   # tiles/s
SPRINT_FACTOR = 1.65               # velocidad al correr con Shift
SPRINT_DRAIN = 34.0                # resistencia consumida por segundo
SPRINT_REGEN = 22.0                # resistencia recuperada por segundo
SPRINT_MAX = 100.0
SPRINT_NOISE_FACTOR = 1.3          # correr amplifica los pasos
SPRINT_MONSTER_MARGIN = 1.05       # al correr, supera por poco la velocidad máxima del monstruo
PEBBLE_PICKUP_COUNT = 6
WEAPON_PICKUP_COUNT = 2
MAGAZINE_SIZE = 6
STARTING_MAGAZINE_AMMO = 3
STARTING_RESERVE_AMMO = 3
AMMO_PICKUP_AMOUNT = 6
WEAPON_RANGE = 18.0
WEAPON_HIT_RADIUS = 0.42
WEAPON_STUN_DURATION = {"facil": 60.0, "medio": 40.0, "dificil": 25.0}
PLAYER_RADIUS = 0.22
CATCH_RADIUS = 0.55                # distancia a la que el monstruo te "toca"
PEBBLE_RANGE = 7.0
SHOUT_RANGE_FACTOR = 2.1
PROXIMA_DOS_MOVE_RANGE = 10
DIFFUSE_PERIOD = 0.4               # cada cuánto se difunde la creencia (s)

# --- pasos del monstruo (audio)
STEP_STRIDE = 0.9                  # tiles que recorre entre un paso y el siguiente
STEP_HEAR_RANGE = 22               # alcance (en pasos de pasillo) con que se oyen sus pasos
PLAYER_REVEAL_TIME = 5.0            # tiempo que el monstruo rastrea la posición exacta
BLUE_POINT_INTERVAL = 120.0        # frecuencia de aparición de marcas azules

# --- niebla tipo Slenderman cuando el monstruo está cerca
FOG_RANGE = 9.0                    # distancia (pasillo) a la que empieza a aparecer la niebla
FOG_LIGHT_LOSS = 0.55              # cuánto se acorta la linterna con la niebla al máximo
FOG_RISE = 2.2                     # qué tan rápido entra/sale la niebla (1/s)


@dataclass(frozen=True)
class Difficulty:
    key: str
    label: str
    algorithm: str        # 'dfs' | 'bfs' | 'astar'
    cells: int            # el laberinto es cells x cells celdas
    braid: float          # prob. de abrir callejones sin salida (crea ciclos)
    monster_speed: float  # tiles/s cuando persigue
    patrol_factor: float  # fracción de velocidad al patrullar
    hear_radius: int      # radio base de un ruido (en pasos de pasillo)
    hear_error: int       # error de localización del sonido (en tiles)
    search_time: float    # segundos que busca antes de rendirse
    noise_density: float  # fracción de tiles ruidosos
    grace: float          # segundos iniciales en que el monstruo está inactivo
    pebbles: int          # piedras para distraer
    minimap: str          # 'full' | 'near' | 'off'
    belief_sigma: float   # dispersión inicial de la creencia
    diffusion: float      # cuánto se "esparce" la creencia por tick
    blurb: str


EASY = Difficulty("facil", "Fácil", "dfs", 8, 0.30, 4.8, 0.55, 13, 4, 8.0, 0.12,
                  14.0, 5, "full", 3.0, 0.25,
                  "DFS: persigue por el primer camino que encuentra, da rodeos.")
MEDIUM = Difficulty("medio", "Medio", "bfs", 10, 0.30, 6.0, 0.75, 17, 2, 14.0, 0.20,
                    6.0, 3, "near", 2.2, 0.20,
                    "BFS: siempre toma el camino más corto, sin atajos de información.")
HARD = Difficulty("dificil", "Difícil", "astar", 12, 0.30, 7.2, 0.85, 21, 1, 22.0, 0.28,
                  4.0, 2, "off", 1.6, 0.15,
                  "A*: camino óptimo ponderado por su creencia de dónde estás.")

DIFFICULTIES = [EASY, MEDIUM, HARD]
BY_KEY = {d.key: d for d in DIFFICULTIES}
