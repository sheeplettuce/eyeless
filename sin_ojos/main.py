"""SIN OJOS - horror en primera persona donde el monstruo solo puede oírte.

Uso:
    python main.py                      # menú
    python main.py --dificultad medio   # saltar menú (facil | medio | dificil)
    python main.py --semilla 42         # mismo laberinto siempre
    python main.py --debug              # empieza con el modo dev activado (F1 / casilla)
    python main.py --silencio           # sin audio
"""
import argparse


def main():
    ap = argparse.ArgumentParser(description="SIN OJOS")
    ap.add_argument("--dificultad", choices=["facil", "medio", "dificil"])
    ap.add_argument("--semilla", type=int)
    ap.add_argument("--debug", "--dev", dest="debug", action="store_true")
    ap.add_argument("--silencio", action="store_true")
    args = ap.parse_args()
    from game.app import App
    App(args).run()


if __name__ == "__main__":
    main()
