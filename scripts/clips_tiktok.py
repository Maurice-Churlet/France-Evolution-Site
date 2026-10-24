# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib", "numpy", "imageio-ffmpeg"]
# ///
"""Clips vidéo verticaux (1080x1920, format TikTok) à partir de data/donnees.json.

Usage : uv run scripts/clips_tiktok.py
Produit dans video/ : dette_1958.mp4, dette_macron.mp4, rythme_presidents.mp4,
patrimoine_1pct.mp4.
Le haut et le bas de l'image sont laissés libres pour les textes ajoutés au montage
(CapCut) et pour les boutons de TikTok.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import imageio_ffmpeg
import matplotlib
import matplotlib.ticker

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
    """Nombre à la française : 55 125 ; 2,03 ; −7,4."""
    texte = f"{v:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return texte.replace("-", "−")


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
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True, nbins=6))  # années entières
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


def reelle(xs, ys, t):
    """Dernier point réellement publié à l'abscisse t (jamais une valeur interpolée)."""
    n = max(1, sum(1 for x in xs if x <= t))
    return xs[n - 1], ys[n - 1]


def jusqua(xs, ys, t):
    """Points de la courbe jusqu'à l'abscisse t, avec un point interpolé au bout."""
    px = [x for x in xs if x <= t]
    py = ys[:len(px)]
    if px and len(px) < len(xs):
        x0, x1, y0, y1 = xs[len(px) - 1], xs[len(px)], ys[len(px) - 1], ys[len(px)]
        py = py + [y0 + (y1 - y0) * (t - x0) / (x1 - x0)]
        px = px + [t]
    return px, py


def clip_courbe(donnees: dict, xs: list, ys: list, ymax: float, titre_axe: str,
                legende, sources: str, nom: str, taille_legende: int = 40,
                debut: int = 1959) -> None:
    """Courbe qui se trace à partir de `debut` sur fond des présidences, avec compteur.

    `legende(t)` donne le texte sous le compteur quand la courbe atteint l'abscisse t.
    """
    xs, ys = zip(*[(x, y) for x, y in zip(xs, ys) if x >= debut])
    xs, ys = list(xs), list(ys)
    fig, ax = figure()
    ax.set_xlim(debut, xs[-1] + 0.5)
    ax.set_ylim(0, ymax)
    ax.set_ylabel(titre_axe, fontsize=24)
    for i, p in enumerate(donnees["presidences"]):
        fin = min(p["fin"], xs[-1])
        if fin <= debut:
            continue
        ax.axvspan(p["debut"], fin, color=BLANC, alpha=0.07 if i % 2 else 0.0, lw=0)
        # Nom en haut de la bande, sauf quand la courbe y monte : il passe alors en bas.
        haut = max(y for x, y in zip(xs, ys) if p["debut"] <= x <= fin) > 0.73 * ymax
        ax.text((max(p["debut"], debut) + fin) / 2, 0.03 * ymax if haut else 0.98 * ymax, p["court"],
                rotation=90, ha="center", va="bottom" if haut else "top", fontsize=20, color=GRIS)
    ligne, = ax.plot([], [], color=ROUGE, lw=6, solid_capstyle="round")
    point, = ax.plot([], [], "o", color=BLANC, ms=16)
    compteur = fig.text(0.5, 0.73, "", ha="center", fontsize=150, fontweight="bold")
    sous_titre = fig.text(0.5, 0.70, "", ha="center", fontsize=taille_legende, color=GRIS)
    fig.text(0.5, 0.255, sources, ha="center", fontsize=22, color=GRIS)

    trace, pause = 9 * IPS, 2 * IPS

    def maj(i):
        t = xs[0] + (xs[-1] - xs[0]) * adouci(i / trace)
        px, py = jusqua(xs, ys, t)
        ligne.set_data(px, py)
        point.set_data([px[-1]], [py[-1]])
        x_reel, y_reel = reelle(xs, ys, t)
        compteur.set_text(f"{fr(y_reel)} %")
        sous_titre.set_text(legende(x_reel))

    enregistrer(fig, maj, trace + pause, nom)


def clip_dette_longue(donnees: dict) -> None:
    xs, ys = serie_dette(donnees)
    clip_courbe(donnees, xs, ys, 130, "Dette publique (% du PIB)",
                lambda t: f"de dette publique · fin {int(t) - 1}",
                "Sources : FMI, Eurostat, Insee", "dette_1958.mp4")


def clip_patrimoine(donnees: dict) -> None:
    valeurs = donnees["series"]["patrimoine"]["valeurs"]
    xs = [int(a) + 0.5 for a in valeurs]  # estimation annuelle : milieu de l'année
    clip_courbe(donnees, xs, list(valeurs.values()), 40, "Part du patrimoine total (%)",
                lambda t: f"du patrimoine aux 1 % les plus riches · {int(t - 0.5)}",
                "Source : World Inequality Database (WID.world)", "patrimoine_1pct.mp4",
                taille_legende=30, debut=1981)


# Clips « classement mondial » : un par graphique du site qui a un rang, limité aux années
# classées. « valeur » est un modèle où {v} reçoit la valeur de l'année ; « axe » remplace
# au besoin le titre de l'axe de gauche.
CLIPS_RANG = {
    "sante": {"valeur": "{v} % du PIB en dépenses de santé", "rang": "rang mondial · espérance de vie",
              "source": "Sources : OCDE, Banque mondiale", "fichier": "rang_sante.mp4"},
    "defense": {"valeur": "{v} % du PIB pour la défense", "rang": "rang mondial · budget militaire",
                "source": "Source : SIPRI", "fichier": "rang_defense.mp4"},
    "recherche": {"valeur": "{v} % du PIB pour la recherche",
                  "rang": "rang · effort de recherche (pays OCDE)",
                  "source": "Source : OCDE", "fichier": "rang_recherche.mp4"},
    "economie": {"valeur": "{v} % de croissance du PIB", "rang": "rang mondial · taille du PIB",
                 "source": "Source : Banque mondiale", "fichier": "rang_economie.mp4"},
    "idh": {"valeur": "indice : {v} sur 1", "rang": "rang mondial · développement humain",
            "source": "Source : PNUD (ONU)", "fichier": "rang_idh.mp4",
            "axe": "Indice de développement humain"},
    "niveau_vie": {"valeur": "{v} $ par habitant", "rang": "rang mondial · PIB par habitant",
                   "source": "Source : Banque mondiale (parité de pouvoir d'achat)",
                   "fichier": "rang_niveau_vie.mp4", "axe": "PIB par habitant ($, PPA)",
                   "gauche": 0.17},  # grands nombres : marge élargie
    "bonheur": {"valeur": "satisfaction de vie : {v} sur 10", "rang": "rang mondial · bonheur déclaré",
                "source": "Source : World Happiness Report (Gallup)", "fichier": "rang_bonheur.mp4",
                "axe": "Satisfaction de vie (sur 10)"},
    "prelevements": {"valeur": "{v} % du PIB en impôts et cotisations",
                     "rang": "rang européen · prélèvements obligatoires",
                     "source": "Source : Eurostat", "fichier": "rang_prelevements.mp4"},
}


def ordinal(n: int) -> str:
    return "1er" if n == 1 else f"{n}e"


def clip_rang(donnees: dict, cle: str) -> None:
    """La valeur (bleu, axe gauche) et le rang mondial (rouge, axe droit inversé) se tracent
    ensemble, sur la seule période où le rang existe. Le compteur affiche le rang."""
    clip = CLIPS_RANG[cle]
    s = donnees["series"][cle]
    annees_rang = sorted(int(a) for a in s["rang"])
    a0, a1 = annees_rang[0], annees_rang[-1]
    # Années non classées : NaN, pour laisser un trou plutôt que relier deux points éloignés.
    rx = [a + 0.5 for a in range(a0, a1 + 1)]
    ry = [s["rang"][str(a)][0] if str(a) in s["rang"] else float("nan") for a in range(a0, a1 + 1)]
    vx = [int(a) + 0.5 for a in s["valeurs"] if a0 <= int(a) <= a1]
    vy = [v for a, v in s["valeurs"].items() if a0 <= int(a) <= a1]
    decimales = s.get("decimales", 2 if cle in ("defense", "recherche") else 1)

    fig, ax = figure(gauche=clip.get("gauche", 0.11))
    ax.set_xlim(a0, a1 + 1)
    marge = (max(vy) - min(vy)) * 0.15 or 0.5
    ax.set_ylim(min(vy) - marge, max(vy) + marge)
    ax.set_ylabel(clip.get("axe", f"{s['titre']} ({s['unite']})"), fontsize=22, color=GRIS)
    ax2 = ax.twinx()
    ax2.set_ylim(max(r for r in ry if r == r) + 0.5, max(0.5, min(r for r in ry if r == r) - 0.5))
    ax2.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ordinal(int(v))))
    ax2.tick_params(labelsize=22, colors=ROUGE)
    for cote in ("top", "left", "bottom"):
        ax2.spines[cote].set_visible(False)
    ax2.spines["right"].set_color(ROUGE)
    for i, p in enumerate(donnees["presidences"]):
        gauche, droite = max(p["debut"], a0), min(p["fin"], a1 + 1)
        if droite - gauche < 2:
            continue  # bande trop étroite pour un nom lisible
        ax.axvspan(gauche, droite, color=BLANC, alpha=0.07 if i % 2 else 0.0, lw=0)
        ax.text((gauche + droite) / 2, 1.01, p["court"], transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=17, color=GRIS)
    ligne_v, = ax.plot([], [], color="#7fa6ff", lw=4)
    ligne_r, = ax2.plot([], [], color=ROUGE, lw=6, solid_capstyle="round")
    point, = ax2.plot([], [], "o", color=BLANC, ms=16)
    compteur = fig.text(0.5, 0.765, "", ha="center", fontsize=150, fontweight="bold")
    sous_titre = fig.text(0.5, 0.735, "", ha="center", fontsize=32, color=GRIS)
    valeur = fig.text(0.5, 0.705, "", ha="center", fontsize=32, color="#7fa6ff")
    fig.text(0.5, 0.255, clip["source"], ha="center", fontsize=22, color=GRIS)

    trace, pause = 8 * IPS, 2 * IPS

    def maj(i):
        t = rx[0] + (rx[-1] - rx[0]) * adouci(i / trace)
        px, py = jusqua(vx, vy, t)
        ligne_v.set_data(px, py)
        n = sum(1 for x in rx if x <= t)
        ligne_r.set_data(rx[:n], ry[:n])
        connus = [(x, r) for x, r in zip(rx[:n], ry[:n]) if r == r]
        if connus:
            x, r = connus[-1]
            point.set_data([x], [r])
            compteur.set_text(ordinal(int(r)))
            sous_titre.set_text(f"{clip['rang']} · {int(x)}")
        if py:
            valeur.set_text(clip["valeur"].format(v=fr(reelle(vx, vy, t)[1], decimales)))

    enregistrer(fig, maj, trace + pause, clip["fichier"])


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
        x_reel, y_reel = reelle(xs, ys, t)
        compteur.set_text(f"{fr(y_reel)} %")
        if x_reel >= xs[-1]:
            legende.set_text(f"de dette publique · mi-{annee_t}")
        else:
            legende.set_text(f"de dette publique · fin {int(x_reel) - 1}")

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


def clip_pisa(donnees: dict) -> None:
    """Scores PISA de la France (maths en rouge, lecture en bleu clair) depuis 2000."""
    pisa = donnees["series"]["education"]["pisa"]
    mx = [int(a) + 0.5 for a in pisa["maths"]]
    my = list(pisa["maths"].values())
    lx = [int(a) + 0.5 for a in pisa["lecture"]]
    ly = list(pisa["lecture"].values())

    fig, ax = figure()
    ax.set_xlim(2000, mx[-1] + 1)
    ax.set_ylim(440, 530)
    ax.set_ylabel("Score PISA (axe zoomé)", fontsize=24)
    for i, p in enumerate(donnees["presidences"]):
        gauche, droite = max(p["debut"], 2000), min(p["fin"], mx[-1] + 1)
        if droite - gauche < 2:
            continue
        ax.axvspan(gauche, droite, color=BLANC, alpha=0.07 if i % 2 else 0.0, lw=0)
        ax.text((gauche + droite) / 2, 1.01, p["court"], transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=17, color=GRIS)
    ligne_m, = ax.plot([], [], color=ROUGE, lw=6, marker="o", ms=10, solid_capstyle="round")
    ligne_l, = ax.plot([], [], color="#7fa6ff", lw=4, marker="o", ms=8)
    point, = ax.plot([], [], "o", color=BLANC, ms=16)
    ax.text(0.98, 0.95, "maths", transform=ax.transAxes, ha="right", fontsize=24, color=ROUGE)
    ax.text(0.98, 0.89, "lecture", transform=ax.transAxes, ha="right", fontsize=24, color="#7fa6ff")
    compteur = fig.text(0.5, 0.765, "", ha="center", fontsize=150, fontweight="bold")
    sous_titre = fig.text(0.5, 0.735, "", ha="center", fontsize=32, color=GRIS)
    lecture = fig.text(0.5, 0.705, "", ha="center", fontsize=32, color="#7fa6ff")
    fig.text(0.5, 0.255, "Sources : OCDE (PISA), DEPP", ha="center", fontsize=22, color=GRIS)

    trace, pause = 8 * IPS, 2 * IPS

    def maj(i):
        t = mx[0] + (mx[-1] - mx[0]) * adouci(i / trace)
        px, py = jusqua(mx, my, t)
        qx, qy = jusqua(lx, ly, t)
        ligne_m.set_data(px, py)
        ligne_l.set_data(qx, qy)
        point.set_data([px[-1]], [py[-1]])
        # Valeurs des seules années d'enquête (tous les 3 ans), jamais interpolées.
        x_m, y_m = reelle(mx, my, t)
        compteur.set_text(f"{y_m:.0f}")
        sous_titre.set_text(f"points en maths à 15 ans · {int(x_m)}")
        lecture.set_text(f"compréhension de l'écrit : {reelle(lx, ly, t)[1]:.0f} points")

    enregistrer(fig, maj, trace + pause, "pisa.mp4")


def main() -> None:
    donnees = json.loads((RACINE / "data" / "donnees.json").read_text(encoding="utf-8"))
    clip_dette_longue(donnees)
    clip_dette_macron(donnees)
    clip_rythme(donnees)
    clip_patrimoine(donnees)
    for cle in CLIPS_RANG:
        clip_rang(donnees, cle)
    clip_pisa(donnees)


if __name__ == "__main__":
    main()
