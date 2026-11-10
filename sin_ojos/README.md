# SIN OJOS

Horror en primera persona dentro de un laberinto. Hay un monstruo que **no puede verte, solo oírte**.
Llega a la luz verde del final sin que te encuentre. No hay sustos: si te alcanza, simplemente pierdes.

## Instalar y jugar

```bash
pip install -r requirements.txt     # solo pygame
python main.py                      # menú de dificultad
python main.py --dificultad medio   # facil | medio | dificil
python main.py --semilla 42         # mismo laberinto siempre
python main.py --dev                # arranca con el modo dev activado (también --debug)
python main.py --silencio           # sin audio
```

El menú usa Engravers MT si está instalada o disponible como `game/assets/EngraversMT.ttf`;
si no, usa Bookman Old Style. Los textos del juego usan Times New Roman.

| Tecla | Acción |
|---|---|
| W A S D | moverse |
| Ratón o ← → | girar |
| Shift | correr (más rápido que el monstruo; consume resistencia que se regenera al soltarlo) |
| Espacio | lanzar una piedra (distracción, hace ruido donde cae) |
| 1–5 | seleccionar un espacio del inventario |
| Clic izquierdo | usar el espacio seleccionado: piedra en 1, arma en 2 |
| F | disparar |
| R | recargar hasta seis balas; empiezas con tres cargadas y tres de reserva |
| Clic derecho | gritar «¡Hey!» (el monstruo lo oye a más distancia que un paso) |
| Tab | minimapa (si el modo lo permite) |
| F1 | **modo dev** (o la casilla "Modo dev", abajo a la derecha en menú/pausa/final): specs, mapa y árbol de búsqueda del monstruo |
| Esc | pausa |

Shift mantiene la carrera mientras haya resistencia; al agotarse, el jugador vuelve a caminar y la
barra azul se recupera al soltarlo. Hay piedras y dos cajas de munición recogibles en las habitaciones
de cada laberinto; cada mapa genera cinco habitaciones de tamaños variados. Las piedras se suman al inventario
y desaparecen al recogerlas. Cada caja añade seis
balas a la reserva. Si un disparo alcanza al monstruo,
lo incapacita sin matarlo durante 60 s en Fácil, 40 s en Medio o 25 s en Difícil. Los puntos azules
son escasos (2/3/4 según dificultad) y aparecen nuevos cada 120 segundos.
El HUD indica la distancia por pasillos y hacia qué lado girar para llegar a la salida.
Al perder aparece brevemente una silueta original en primer plano con distorsión visual y un
efecto de estática digital; no se usa el rugido del monstruo durante el susto.
Los tiles ruidosos son manchas de piso crujiente distribuidas con **ruido de Perlin**. Se sombrean
apenas más que el suelo normal y se mezclan con manchas oscuras de Perlin de mayor contraste, tanto
en el suelo como en los mapas, para que no sea fácil identificarlos. Pisarlos suena (¡ruido! en
pantalla) y el monstruo puede oírlo a mayor distancia; cada ruido interrumpe su búsqueda actual.
Durante cinco segundos conoce la ubicación exacta del jugador y lo rastrea si sigue moviéndose.

**Audio:** los pasos del monstruo se oyen cada 0.9 tiles que recorre, con volumen según la distancia
por pasillos (alcance 22 pasos) y espacialización estéreo aproximada. La respiración del jugador suena
al correr y continúa un poco al parar; la respiración del monstruo aumenta al acercarse. También
el monstruo reproduce periódicamente frases aleatorias del banco, incluido `GRUNIDO`, tanto en patrulla
como al perseguir. Las tres variantes de «¡Hey!» también usan ese banco; pygame reproduce las versiones
WAV que acompañan a los originales M4A. La vista lleva un marco de cámara, líneas de barrido y un
indicador REC dibujados por Pygame, sin conexión ni dependencias de shaders. «Próxima dos move» solo suena cuando el monstruo está a diez
pasos de pasillo o menos; al acertarle un disparo, «Sobbing» suena en bucle y en exclusiva hasta que el
monstruo se recupera. «Scream» únicamente suena al perder en el jumpscare. No se necesita instalar un
TTS ni tener internet para jugar.

El monstruo conserva su silueta humanoide oscura original, con movimiento procedural sutil. Las piedras
se ven en vuelo, siguen una trayectoria arqueada, hacen ruido al impactar y permanecen brevemente
visibles en ese punto.

**Niebla estilo Slenderman:** cuando el monstruo está a menos de ~9 pasos de pasillo, la pantalla se
llena de niebla que se cierra poco a poco (y la linterna alcanza menos). Se disipa al alejarte.
El monstruo "emerge" de la niebla en vez de desaparecer. Ajustable con `FOG_*` en `game/config.py`.

## Modo dev

Actívalo con la **casilla "Modo dev"** (esquina inferior derecha; se puede clicar en el menú, la pausa
y la pantalla final, porque en juego el ratón está capturado) o con **F1** en cualquier momento.

* **Panel compacto dentro de la pantalla**: el mapa está a la derecha y las especificaciones del
  monstruo, su búsqueda y la resistencia aparecen abajo. El modo dev no cambia ni recorta la ventana.
* **El algoritmo, nodo por nodo:** cada vez que el monstruo planifica se reproduce la búsqueda como un
  **árbol de nodos** (azul → cian en orden de expansión, el círculo blanco es el nodo que se está
  expandiendo, los aros naranjas son la frontera que quedó sin expandir). Al terminar aparece el
  **camino** final en amarillo y la meta (X magenta). DFS, BFS y A* se ven muy distintos.
* **Especificaciones:** estado, tile y posición exactos, meta, velocidad actual/base, radio y error de
  oído, tiempo de búsqueda, distancia a ti (recta y por pasillo), niebla, algoritmo y su estructura de
  datos, replanificaciones, nodos expandidos (último/total/por plan), costo, σ y difusión de la creencia.


## Cómo piensa el monstruo

1. **Oído por pasillos.** El ruido se propaga con BFS por el laberinto (no en línea recta). Si el
   monstruo está dentro del radio, lo oye con probabilidad decreciente con la distancia.
2. **Localización imperfecta.** No sabe el tile exacto: percibe uno cercano, con error mayor
   si el sonido vino de lejos.
3. **Creencia (mapa de probabilidad).** Al oír algo concentra una gaussiana alrededor del punto
   percibido. Cada 0.4 s la creencia se **difunde** a tiles vecinas (pudiste moverte) y se **borra**
   donde el monstruo ya miró.
4. **Estados:** `PATRULLA` → (oye algo) → `INVESTIGA` → (llega) → `BUSCA` (barre las zonas
   de mayor probabilidad) → (se rinde) → `PATRULLA`.
5. **Planificación.** Para ir a cualquier meta usa el algoritmo de la dificultad:
   DFS, BFS o A* (`game/pathfinding.py`). Todo es código propio; no hay APIs externas.

## Valoración: ¿qué algoritmo para qué dificultad?

Importante: en un laberinto "perfecto" (sin ciclos) hay un solo camino entre dos puntos, y los tres
algoritmos darían la misma ruta. Por eso el generador abre callejones y crea ciclos (`braid`).

**Benchmark estático** (`python tools/benchmark.py`, laberinto 10x10, medias):

| Algoritmo | Largo vs. óptimo | Nodos expandidos |
|---|---|---|
| DFS puro (vecinos al azar) | 1.9–2.9× | ~100 |
| BFS | 1.00× | ~106 |
| A* (Manhattan) | 1.00× | ~83 |

**Escenario de cacería** (`python tools/simulate.py`, jugador quieto haciendo ruido; tiempo medio hasta ser atrapado; velocidades del monstruo: 4.8 / 6.0 / 7.2 tiles/s, el jugador camina a 2.6):

| Dificultad | DFS | BFS | A* |
|---|---|---|---|
| Fácil | **31.4 s** | 24.5 s | 24.4 s |
| Medio | 17.5 s | **11.9 s** | 11.9 s |
| Difícil | 23.7 s | 10.0 s | **10.0 s** |

Conclusiones:

* **Fácil → DFS.** No garantiza el camino más corto: da rodeos y tarda claramente más en llegar
  (1.3× más en Fácil, hasta 2.4× en Difícil). Se siente como un monstruo torpe, que es lo que queremos.
* **Medio → BFS.** Siempre toma el camino más corto en pasos. Es "competente pero sin trucos".
* **Difícil → A*.** Produce el mismo largo que BFS pero expande ~20–25 % menos nodos, y es el
  único de los tres que admite **costos por tile**: aquí pondera cada tile según la creencia
  (los tiles probables cuestan menos), así que sus rutas pasan por donde es más probable que estés.
* **Honestidad:** BFS y A* se comportan casi igual en juego; la diferencia real entre ellos es
  eficiencia y capacidad de usar pesos, no "inteligencia" visible. Lo que separa de verdad las
  dificultades son los demás parámetros (velocidad, radio de oído, error de localización, tiempo
  de búsqueda, densidad de ruido, minimapa) en `game/config.py` (`monster_speed` de cada dificultad
fija lo rápido que es el monstruo). Puedes cruzar cualquier
  dificultad con cualquier algoritmo editando el campo `algorithm`.

Resultados completos de la simulación: `tools/resultados_simulacion.txt`.

## Estructura

```
main.py                 punto de entrada
game/config.py          constantes y las 3 dificultades
game/maze.py            generación (DFS + ciclos) y distancias
game/perlin.py          ruido de Perlin propio
game/noisemap.py        reparte los tiles ruidosos con Perlin
game/pathfinding.py     DFS, BFS y A*
game/monster.py         estados, oído, creencia y movimiento
game/world.py           reglas del juego (sin pygame: se puede simular)
game/render.py          raycaster en primera persona, linterna, sprites
game/audio.py           paneo estéreo y voces susurradas
game/assets/SOUNDS/     voces del jugador y del monstruo
game/debug_view.py      modo dev: mapa, specs y árbol de búsqueda animado
game/app.py             ventana, menús y HUD
tools/benchmark.py      compara algoritmos sin jugar
tools/simulate.py       bot vs monstruo, dificultad x algoritmo
tests/test_smoke.py     pruebas:  python -m unittest discover tests
```

## Ideas para ampliar

* Que el monstruo aprenda tus rutas favoritas (mapa de hábitos) y las patrulle más.
* Q-learning o un agente entrenado para decidir adónde buscar.
* Más tipos de ruido (puertas, objetos que caen) con radios distintos.
* Texturas e imágenes reales en lugar de las procedurales.
