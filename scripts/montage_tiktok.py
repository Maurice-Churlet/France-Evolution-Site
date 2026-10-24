# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts", "pillow", "imageio-ffmpeg"]
# ///
"""Monte la vidéo TikTok complète : clips de video/, voix de synthèse, sous-titres incrustés
et carton final. Produit video/tiktok_merci_macron.mp4 (1080x1920, sans musique : elle
s'ajoute dans l'application TikTok, dont la bibliothèque est sous licence).

Usage : uv run scripts/montage_tiktok.py   (régénérer d'abord les clips avec clips_tiktok.py)
La voix est produite par le service de lecture à voix haute de Microsoft (edge-tts) :
le texte du script lui est envoyé.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).resolve().parent.parent
VIDEO = RACINE / "video"
SORTIE = VIDEO / "tiktok_merci_macron.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOIX = "fr-FR-HenriNeural"
DEBIT = "+6%"
LARGEUR, HAUTEUR, IPS = 1080, 1920, 30
POLICE = "C:/Windows/Fonts/segoeuib.ttf"

# (clip, texte lu). Chiffres repris de data/donnees.json au 24/10/2026.
SEQUENCES = [
    ("dette_1958.mp4", "Merci Macron ! En 1958, la dette, c'est 32 % du PIB. Elle fond sous de "
                       "Gaulle… puis elle ne fait plus que monter. Fin 2025 : 115,7 %."),
    ("dette_macron.mp4", "Macron hérite de 98 %. Le Covid passe par là… on pardonne. Mais le Covid "
                         "est fini, et la dette grimpe encore : 119 % à la mi-2026."),
    ("rythme_presidents.mp4", "Rassurez-vous : le champion de vitesse reste Sarkozy, plus 4,7 points "
                              "par an. Macron ? Seulement 2. Petit joueur."),
    ("rang_prelevements.mp4", "Et pour payer tout ça ? 45 % du PIB en impôts et cotisations, selon "
                              "Eurostat. Deuxièmes d'Europe… et même premiers en 2022 et 2023. "
                              "Merci qui ?"),
    ("rang_bonheur.mp4", "Et le moral ? En 2021, la France était 20e au classement mondial du "
                         "bonheur. Aujourd'hui : 35e. On se demande bien pourquoi."),
    ("patrimoine_1pct.mp4", "Bonne nouvelle quand même : les 1 % les plus riches vont très bien. "
                            "16 % du patrimoine en 1984… près de 28 % aujourd'hui."),
]
# Carton final : la question (lue et affichée), puis les sources et l'adresse du site.
QUESTION_LUE = ("Et si nos politiques répondaient de leurs résultats… sur leurs biens propres ? "
                "Vous pensez que ça irait mieux ? Dites-le en commentaire.")
QUESTION = ["Et si nos politiques", "répondaient de leurs", "résultats… sur leurs",
            "biens propres ?", "", "Ça irait mieux ?", "Dites-le en commentaire !"]
SOURCES = ["Tous les chiffres et les sources :", "Insee · Eurostat · ONU · FMI",
           "maurice-churlet.github.io/France-Evolution-Site"]


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", *args], check=True)


def duree(fichier: Path) -> float:
    """Durée d'un fichier audio ou vidéo, lue dans la sortie de ffmpeg."""
    sortie = subprocess.run([FFMPEG, "-i", str(fichier)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", sortie).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def morceaux(texte: str, longueur_max: int = 26) -> list[str]:
    """Découpe le texte en petits groupes de mots, affichés l'un après l'autre (style TikTok)."""
    groupes, courant = [], ""
    for mot in texte.split():
        if courant and len(courant) + 1 + len(mot) > longueur_max:
            groupes.append(courant)
            courant = mot
        else:
            courant = f"{courant} {mot}".strip()
        if mot.endswith((".", "?", "!", "…", ":")) and len(courant) > 10:
            groupes.append(courant)
            courant = ""
    if courant:
        groupes.append(courant)
    return groupes


def image_texte(lignes: list[str], chemin: Path, taille: int, fond: bool, y_centre: int,
                pied: list[str] | None = None) -> None:
    """PNG 1080x1920 : texte blanc cerné de noir (sous-titre) ou carton sur fond bleu,
    avec, en option, quelques lignes plus petites en bas (`pied`)."""
    img = Image.new("RGBA", (LARGEUR, HAUTEUR), (15, 42, 99, 255) if fond else (0, 0, 0, 0))
    dessin = ImageDraw.Draw(img)
    if pied:
        petite = ImageFont.truetype(POLICE, 38)
        for k, ligne in enumerate(pied):
            dessin.text((LARGEUR // 2, 1330 + k * 52), ligne, font=petite, fill="#9fb1d9", anchor="ma")
    police = ImageFont.truetype(POLICE, taille)
    hauteur_ligne = int(taille * 1.25)
    y = y_centre - hauteur_ligne * len(lignes) // 2
    for ligne in lignes:
        dessin.text((LARGEUR // 2, y), ligne, font=police, fill="white", anchor="ma",
                    stroke_width=0 if fond else 6, stroke_fill="black")
        y += hauteur_ligne
    img.save(chemin)


async def voix(texte: str, chemin: Path) -> None:
    await edge_tts.Communicate(texte, VOIX, rate=DEBIT).save(str(chemin))


def sequence(i: int, clip: str, texte: str, tmp: Path) -> Path:
    """Un segment : clip (prolongé sur sa dernière image si la voix est plus longue),
    voix, et sous-titres en haut de l'écran, au-dessus du compteur."""
    audio = tmp / f"voix{i}.mp3"
    asyncio.run(voix(texte, audio))
    d_voix, d_clip = duree(audio), duree(VIDEO / clip)
    total = max(d_clip, d_voix + 0.5)

    groupes = morceaux(texte)
    poids = [len(g) for g in groupes]
    entrees, filtres, debut, courant = [], [], 0.1, "[0:v]"
    for j, (g, p) in enumerate(zip(groupes, poids)):
        fin = debut + d_voix * p / sum(poids)
        png = tmp / f"st{i}_{j}.png"
        image_texte([g], png, 62, fond=False, y_centre=255)
        entrees += ["-i", str(png)]
        sortie = f"[v{j}]"
        filtres.append(f"{courant}[{j + 2}:v]overlay=0:0:enable='between(t,{debut:.2f},{fin:.2f})'{sortie}")
        courant, debut = sortie, fin
    prolonge = f"[0:v]tpad=stop_mode=clone:stop_duration={max(0, total - d_clip):.2f}[base]"
    filtres[0] = filtres[0].replace("[0:v]", "[base]", 1)
    graphe = ";".join([prolonge, *filtres])

    resultat = tmp / f"seq{i}.mp4"
    ffmpeg("-i", str(VIDEO / clip), "-i", str(audio), *entrees,
           "-filter_complex", graphe, "-map", courant, "-map", "1:a",
           "-af", f"apad=whole_dur={total:.2f}", "-t", f"{total:.2f}",
           "-r", str(IPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(resultat))
    return resultat


def carton(tmp: Path) -> Path:
    """Carton final : question lue par la voix, sources et adresse en bas."""
    audio = tmp / "voix_question.mp3"
    asyncio.run(voix(QUESTION_LUE, audio))
    total = duree(audio) + 1.5
    png = tmp / "carton.png"
    image_texte(QUESTION, png, 72, fond=True, y_centre=760, pied=SOURCES)
    resultat = tmp / "carton.mp4"
    ffmpeg("-loop", "1", "-i", str(png), "-i", str(audio), "-af", f"apad=whole_dur={total:.2f}",
           "-t", f"{total:.2f}", "-r", str(IPS), "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(resultat))
    return resultat


def main() -> None:
    manquants = [c for c, _ in SEQUENCES if not (VIDEO / c).exists()]
    if manquants:
        raise SystemExit(f"Clips manquants dans video/ : {manquants} (lancer clips_tiktok.py)")
    with tempfile.TemporaryDirectory() as dossier:
        tmp = Path(dossier)
        morceaux_video = [sequence(i, c, t, tmp) for i, (c, t) in enumerate(SEQUENCES)]
        morceaux_video.append(carton(tmp))
        liste = tmp / "liste.txt"
        liste.write_text("".join(f"file '{m.as_posix()}'\n" for m in morceaux_video), encoding="utf-8")
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy",
               "-movflags", "+faststart", str(SORTIE))
    print(f"Écrit : video/{SORTIE.name} ({duree(SORTIE):.1f} s)")


if __name__ == "__main__":
    main()
