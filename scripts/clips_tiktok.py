# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib", "numpy", "imageio-ffmpeg"]
# ///
"""Clips vidéo verticaux (1080x1920, format TikTok) à partir de data/donnees.json.

Usage : uv run scripts/clips_tiktok.py
Produit dans video/ : dette_1958.mp4, dette_macron.mp4, rythme_presidents.mp4.
Le haut et le bas de l'image sont laissés libres pour les textes ajoutés au montage
(CapCut) et pour les boutons de TikTok.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "video"
IPS = 30  # images par seconde

FOND = "#0f2a63"
BLANC = "#ffffff"
ROUGE = "#ff3b47"
ORANGE = "#ffb020"
VERT = "#3ddc84"
GRIS = "#9fb1d9"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "animation.ffmpeg_path": imageio_ffmpeg.get_ffmpeg_exe(),
    "axes.facecolor": FOND,
    "figure.facecolor": FOND,
    "text.color": BLANC,
    "axes.labelcolor": GRIS,
    "xtick.color": GRIS,
    "ytick.color": GRIS,
})


def fr(v: float, decimales: int = 1) -> str:
    return f"{v:.{decimales}f}".replace(".", ",").replace("-", "−")


def adouci(p: float) -> float:
    """Progression 0→1 avec départ et arrivée en douceur."""
    p = min(max(p, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * p)


def figure(gauche: float = 0.11):
    fig = plt.figure(figsize=(10.8, 19.2), dpi=100)
    ax = fig.add_axes((gauche, 0.30, 0.91 - gauche, 0.36))  # zone sûre : ni le haut ni le bas
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(GRIS)
    ax.tick_params(labelsize=22)
    ax.grid(axis="y", color="#2a4585", lw=1)
    return fig, ax


def enregistrer(fig, maj, nb_images: int, nom: str) -> None:
    SORTIE.mkdir(exist_ok=True)
    anim = FuncAnimation(fig, maj, frames=nb_images, blit=False)
    anim.save(SORTIE / nom, writer=FFMpegWriter(fps=IPS, bitrate=6000, codec="libx264",
                                                 extra_args=["-pix_fmt", "yuv420p"]))
    plt.close(fig)
    print(f"Écrit : video/{nom}")


def serie_dette(donnees: dict) -> tuple[list[float], list[float]]:
    # Encours au 31 décembre : placé au début de l'année suivante, comme sur le site.
    valeurs = donnees["series"]["dette"]["valeurs"]
    return [int(a) + 1 for a in valeurs], list(valeurs.values())


def jusqua(xs, ys, t):
    """Points de la courbe jusqu'à l'abscisse t, avec un point interpolé au bout."""
    px = [x for x in xs if x <= t]
    py = ys[:len(px)]
    if px and len(px) < len(xs):
        x0, x1, y0, y1 = xs[len(px) - 1], xs[len(px)], ys[len(px) - 1], ys[len(px)]
        py = py + [y0 + (y1 - y0) * (t - x0) / (x1 - x0)]
        px = px + [t]
    return px, py


def clip_dette_longue(donnees: dict) -> None:
    xs, ys = serie_dette(donnees)
    xs, ys = zip(*[(x, y) for x, y in zip(xs, ys) if x >= 1959])
    xs, ys = list(xs), list(ys)
    fig, ax = figure()
    ax.set_xlim(1959, xs[-1] + 0.5)
    ax.set_ylim(0, 130)
    ax.set_ylabel("Dette publique (% du PIB)", fontsize=24)
    for i, p in enumerate(donnees["presidences"]):
        fin = min(p["fin"], xs[-1])
        ax.axvspan(p["debut"], fin, color=BLANC, alpha=0.07 if i % 2 else 0.0, lw=0)
        # Nom en haut de la bande, sauf quand la courbe y monte : il passe alors en bas.
        haut = max(y for x, y in zip(xs, ys) if p["debut"] <= x <= fin) > 95
        ax.text((p["debut"] + fin) / 2, 4 if haut else 127, p["court"], rotation=90, ha="center",
                va="bottom" if haut else "top", fontsize=20, color=GRIS)
    ligne, = ax.plot([], [], color=ROUGE, lw=6, solid_capstyle="round")
    point, = ax.plot([], [], "o", color=BLANC, ms=16)
    compteur = fig.text(0.5, 0.73, "", ha="center", fontsize=150, fontweight="bold")
    annee = fig.text(0.5, 0.70, "", ha="center", fontsize=40, color=GRIS)
    fig.text(0.5, 0.255, "Sources : FMI, Eurostat, Insee", ha="center", fontsize=22, color=GRIS)

    trace, pause = 9 * IPS, 2 * IPS

    def maj(i):
        t = xs[0] + (xs[-1] - xs[0]) * adouci(i / trace)
        px, py = jusqua(xs, ys, t)
        ligne.set_data(px, py)
        point.set_data([px[-1]], [py[-1]])
        compteur.set_text(f"{fr(py[-1])} %")
        annee.set_text(f"de dette publique · fin {int(t) - 1}")

    enregistrer(fig, maj, trace + pause, "dette_1958.mp4")


def clip_dette_macron(donnees: dict) -> None:
    xs, ys = serie_dette(donnees)
    xs, ys = zip(*[(x, y) for x, y in zip(xs, ys) if x >= 2017])
    xs, ys = list(xs), list(ys)
    trim = donnees["series"]["dette"]["dernier_trimestre"]
    annee_t, numero_t = trim["periode"].split("-Q")
    xs.append(int(annee_t) + int(numero_t) / 4)  # fin de trimestre
    ys.append(trim["valeur"])

    fig, ax = figure()
    ax.set_xlim(2016.8, xs[-1] + 0.3)
    ax.set_ylim(90, 125)
    ax.set_ylabel("Dette publique (% du PIB, axe zoomé)", fontsize=24)
    ax.set_xticks(range(2017, int(xs[-1]) + 1, 2))
    ligne, = ax.plot([], [], color=ROUGE, lw=7, solid_capstyle="round")
    point, = ax.plot([], [], "o", color=BLANC, ms=18)
    covid = ax.annotate("Covid", (2021, ys[xs.index(2021)]), xytext=(2018.2, 118), fontsize=30,
                        color=ORANGE, arrowprops={"arrowstyle": "->", "color": ORANGE, "lw": 3})
    covid.set_visible(False)
    compteur = fig.text(0.5, 0.73, "", ha="center", fontsize=150, fontweight="bold")
    legende = fig.text(0.5, 0.70, "", ha="center", fontsize=40, color=GRIS)
    fig.text(0.5, 0.255, "Sources : Eurostat, Insee (dernier trimestre)", ha="center",
             fontsize=22, color=GRIS)

    trace, pause = 7 * IPS, 2 * IPS

    def maj(i):
        t = xs[0] + (xs[-1] - xs[0]) * adouci(i / trace)
        px, py = jusqua(xs, ys, t)
        ligne.set_data(px, py)
        point.set_data([px[-1]], [py[-1]])
        covid.set_visible(t >= 2021)
        compteur.set_text(f"{fr(py[-1])} %")
        if t >= xs[-1]:
            legende.set_text(f"de dette publique · mi-{annee_t}")
        else:
            legende.set_text(f"de dette publique · fin {int(t) - 1}")

    enregistrer(fig, maj, trace + pause, "dette_macron.mp4")


def bilan(valeurs: dict, p: dict) -> tuple[float, int, int]:
    """Variation par an entre fin (début-1) et fin (fin-1), comme sur le site."""
    derniere = max(int(a) for a in valeurs)
    a0, a1 = p["debut"] - 1, min(p["fin"] - 1, derniere)
    return (valeurs[str(a1)] - valeurs[str(a0)]) / (a1 - a0), a0, a1


def clip_rythme(donnees: dict) -> None:
    serie = donnees["series"]["dette"]
    ruptures = serie.get("ruptures", [])
    presidents = []
    for p in donnees["presidences"]:
        par_an, a0, a1 = bilan(serie["valeurs"], p)
        if any(a0 < r <= a1 for r in ruptures):
            continue  # changement de source pendant le mandat : comparaison non fiable
        presidents.append((p["court"], par_an))
    presidents.reverse()  # le plus récent en bas

    fig, ax = figure(gauche=0.26)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=30, colors=BLANC)
    ax.set_xlim(-2.5, 6)
    ax.axvline(0, color=GRIS, lw=2)
    ax.set_xlabel("Hausse de la dette, en points de PIB par an", fontsize=24)
    noms = [n for n, _ in presidents]
    couleurs = [ROUGE if n == "Sarkozy" else ORANGE if n == "Macron" else
                VERT if v < 0 else GRIS for n, v in presidents]
    barres = ax.barh(noms, [0] * len(noms), color=couleurs, height=0.6)
    etiquettes = [ax.text(0, i, "", va="center", fontsize=30, fontweight="bold")
                  for i in range(len(noms))]
    fig.text(0.5, 0.745, "Qui a creusé", ha="center", fontsize=80, fontweight="bold")
    fig.text(0.5, 0.70, "le plus vite ?", ha="center", fontsize=80, fontweight="bold")
    fig.text(0.5, 0.235, "Sources : Eurostat, FMI · hors Pompidou et Giscard (changement de source)",
             ha="center", fontsize=20, color=GRIS)

    pousse, pause = 4 * IPS, 3 * IPS

    def maj(i):
        e = adouci(i / pousse)
        for barre, etiquette, (_, v), y in zip(barres, etiquettes, presidents, range(len(noms))):
            barre.set_width(v * e)
            # Valeur au bout de la barre ; pour une baisse, à droite du zéro (côté libre).
            etiquette.set_position((v * e + 0.15 if v >= 0 else 0.15, y))
            etiquette.set_ha("left")
            etiquette.set_text(f"{'+' if v > 0 else ''}{fr(v * e)}" if e > 0.05 else "")

    enregistrer(fig, maj, pousse + pause, "rythme_presidents.mp4")


def main() -> None:
    donnees = json.loads((RACINE / "data" / "donnees.json").read_text(encoding="utf-8"))
    clip_dette_longue(donnees)
    clip_dette_macron(donnees)
    clip_rythme(donnees)


if __name__ == "__main__":
    main()
