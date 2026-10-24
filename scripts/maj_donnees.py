# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl", "matplotlib"]
# ///
"""Télécharge les séries officielles et régénère data/donnees.json (+ l'image dette.png).

Usage : uv run scripts/maj_donnees.py
Chaque source est récupérée indépendamment : si l'une échoue, le script s'arrête sans
écraser le fichier existant (mieux vaut des données d'hier que des données partielles).
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "data" / "donnees.json"
IMAGE_DETTE = RACINE / "dette.png"

PRESIDENCES = [
    {"nom": "Charles de Gaulle", "court": "De Gaulle", "debut": 1959, "fin": 1969},
    {"nom": "Georges Pompidou", "court": "Pompidou", "debut": 1969, "fin": 1974},
    {"nom": "Valéry Giscard d'Estaing", "court": "Giscard", "debut": 1974, "fin": 1981},
    {"nom": "François Mitterrand", "court": "Mitterrand", "debut": 1981, "fin": 1995},
    {"nom": "Jacques Chirac", "court": "Chirac", "debut": 1995, "fin": 2007},
    {"nom": "Nicolas Sarkozy", "court": "Sarkozy", "debut": 2007, "fin": 2012},
    {"nom": "François Hollande", "court": "Hollande", "debut": 2012, "fin": 2017},
    {"nom": "Emmanuel Macron", "court": "Macron", "debut": 2017, "fin": 2027, "en_cours": True},
]

# Scores PISA de la France (OCDE). Pas d'API publique simple : valeurs saisies depuis les
# rapports OCDE (2000-2022) et la note DEPP n° 26.40 (2025). À compléter à chaque édition.
PISA = {
    "maths": {"2000": 517, "2003": 511, "2006": 496, "2009": 497, "2012": 495,
              "2015": 493, "2018": 495, "2022": 474, "2025": 458},
    "lecture": {"2000": 505, "2003": 496, "2006": 488, "2009": 496, "2012": 505,
                "2015": 499, "2018": 493, "2022": 474, "2025": 456},
}

# Pays de plus d'un million d'habitants : écarte micro-États et territoires (Monaco, Macao,
# Bermudes...) qui fausseraient les classements de la Banque mondiale.
POPULATION_MIN = 1_000_000

URL_FMI_FPP = "https://www.imf.org/external/datamapper/api/v1/d/FRA"
URL_FMI_GDD = "https://www.imf.org/external/datamapper/api/v1/GG_DEBT_GDP/FRA"
URL_EUROSTAT_DETTE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1"
    "?geo=FR&unit=PC_GDP&sector=S13&na_item=GD&format=JSON"
)
URL_INSEE_DETTE_TRIM = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/010777608?lastNObservations=1"
URL_EUROSTAT_EDUCATION = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10a_exp"
    "?geo=FR&unit=PC_GDP&sector=S13&cofog99=GF09&na_item=TE&format=JSON"
)
URL_SIPRI_PAGE = "https://www.sipri.org/databases/milex"
URL_OECD_RD = (
    "https://sdmx.oecd.org/public/rest/data/OECD.STI.STP,DSD_MSTI@DF_MSTI,/"
    ".A.G.PT_B1GQ.....?format=csvfilewithlabels"
)
URL_OECD_SANTE = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ELS.HD,DSD_SHA@DF_SHA,/"
    "FRA.A.EXP_HEALTH.PT_B1GQ._T.._T.._T...?format=csvfilewithlabels"
)
URL_WB = "https://api.worldbank.org/v2/country/{pays}/indicator/{ind}?format=json&per_page=20000"
URL_WB_PAYS = "https://api.worldbank.org/v2/country?format=json&per_page=400"


def telecharger(url: str, essais: int = 3) -> bytes:
    """GET avec quelques nouvelles tentatives (les API publiques ont des ratés passagers).

    Les serveurs filtrent les navigateurs différemment : le FMI refuse un agent de type
    navigateur, l'OCDE refuse celui de Python. On essaie donc les deux. Une page
    introuvable (404) est une erreur définitive : inutile d'insister.
    """
    agents = [None, "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"]
    derniere_erreur: Exception | None = None
    for essai in range(essais):
        for agent in agents:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": agent} if agent else {})
                with urllib.request.urlopen(req, timeout=120) as rep:
                    return rep.read()
            except urllib.error.HTTPError as e:
                if e.code in (400, 404, 410):
                    raise RuntimeError(f"{url} : erreur HTTP {e.code}") from e
                derniere_erreur = e
            except Exception as e:  # noqa: BLE001 - coupure réseau, délai... : on retente
                derniere_erreur = e
        time.sleep(3 * (essai + 1))
    raise RuntimeError(f"Échec du téléchargement de {url} : {derniere_erreur}")


def arrondi(valeurs: dict[str, float], decimales: int = 1) -> dict[str, float]:
    return {a: round(v, decimales) for a, v in sorted(valeurs.items())}


def oecd_csv(url: str) -> list[dict[str, str]]:
    texte = telecharger(url).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texte)))


def statuts_oecd(lignes: list[dict[str, str]]) -> tuple[list[int], list[int]]:
    """Années de rupture de série (statut B) et valeurs provisoires ou estimées (P, E)."""
    ruptures = sorted(int(l["TIME_PERIOD"]) for l in lignes if l["OBS_STATUS"] == "B")
    provisoires = sorted(int(l["TIME_PERIOD"]) for l in lignes if l["OBS_STATUS"] in ("P", "E"))
    return ruptures, provisoires


def fmi(url: str, indicateur: str) -> dict[str, float]:
    return json.loads(telecharger(url))["values"][indicateur]["FRA"]


def eurostat(url: str) -> dict[str, float]:
    """{année: valeur} d'une requête Eurostat ne portant que sur une série."""
    es = json.loads(telecharger(url))
    if any(taille != 1 for dim, taille in zip(es["id"], es["size"]) if dim != "time"):
        raise RuntimeError(f"Eurostat : la requête renvoie plusieurs séries ({url})")
    annees = {v: k for k, v in es["dimension"]["time"]["category"]["index"].items()}
    return {annees[int(i)]: v for i, v in es["value"].items()}


def banque_mondiale(pays: str, indicateur: str) -> list[dict]:
    donnees = json.loads(telecharger(URL_WB.format(pays=pays, ind=indicateur)))
    if len(donnees) < 2 or not donnees[1]:
        raise RuntimeError(f"Banque mondiale : aucune donnée pour {indicateur}")
    if donnees[0].get("pages", 1) > 1:
        raise RuntimeError(f"Banque mondiale : réponse tronquée pour {indicateur}, augmenter per_page")
    return [x for x in donnees[1] if x["value"] is not None]


_PAYS_BANQUE_MONDIALE: set[str] = set()


def banque_mondiale_monde(indicateur: str, population_min: float = 0) -> dict[str, dict[str, float]]:
    """{année: {pays: valeur}} pour tous les pays (agrégats régionaux exclus)."""
    if not _PAYS_BANQUE_MONDIALE:
        pays = json.loads(telecharger(URL_WB_PAYS))[1]
        _PAYS_BANQUE_MONDIALE.update(p["id"] for p in pays if p["region"]["value"] != "Aggregates")
    population = banque_mondiale_monde("SP.POP.TOTL") if population_min else {}
    par_annee: dict[str, dict[str, float]] = {}
    for x in banque_mondiale("all", indicateur):
        code, annee = x["countryiso3code"], x["date"]
        if code not in _PAYS_BANQUE_MONDIALE:
            continue
        if population_min and population.get(annee, {}).get(code, 0) < population_min:
            continue
        par_annee.setdefault(annee, {})[code] = x["value"]
    return par_annee


def rangs(par_annee: dict[str, dict[str, float]], pays: str, annee_min: int,
          garder_valeur: bool = False) -> dict[str, list]:
    """Par année : [rang de `pays` (1 = valeur la plus haute), nombre de pays classés]
    et, si `garder_valeur`, la valeur de `pays` (affichée dans l'infobulle).

    Les années où trop peu de pays ont publié (souvent les plus récentes) sont écartées :
    un rang calculé sur une liste incomplète flatterait ou pénaliserait la France à tort.
    """
    retenues = {a: v for a, v in par_annee.items() if int(a) >= annee_min and pays in v}
    if not retenues:
        return {}
    couverture_max = max(len(v) for v in retenues.values())
    resultat = {}
    for annee, valeurs in sorted(retenues.items()):
        if len(valeurs) < 0.9 * couverture_max:
            continue
        classes = sorted(valeurs.values(), reverse=True)
        resultat[annee] = [classes.index(valeurs[pays]) + 1, len(classes)]
        if garder_valeur:
            resultat[annee].append(round(valeurs[pays], 1))
    return resultat


# --- Collecte par domaine -------------------------------------------------------------


def dette() -> dict:
    # Trois sources, de la plus ancienne à la plus récente. La Global Debt Database du FMI
    # rejoint exactement Eurostat en 1995 ; la base historique (FPP) a d'autres définitions.
    historique = fmi(URL_FMI_FPP, "d")
    gdd = fmi(URL_FMI_GDD, "GG_DEBT_GDP")
    eurostat_dette = eurostat(URL_EUROSTAT_DETTE)
    if "2010" not in eurostat_dette or "1980" not in gdd:
        raise RuntimeError("FMI / Eurostat : série de dette incomplète")
    valeurs = {a: v for a, v in historique.items() if 1950 <= int(a) < 1978}
    valeurs.update({a: v for a, v in gdd.items() if 1978 <= int(a) < 1995})
    valeurs.update(eurostat_dette)  # 1995+ : dette notifiée par l'Insee à Eurostat

    xml = telecharger(URL_INSEE_DETTE_TRIM).decode("utf-8")
    obs = re.search(r'TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"', xml)
    if not obs:
        raise RuntimeError("Insee : dernier trimestre de dette introuvable")
    return {
        "titre": "Dette publique",
        "unite": "% du PIB",
        "valeurs": arrondi(valeurs),
        "ruptures": [1970, 1978],
        "dernier_trimestre": {"periode": obs.group(1), "valeur": float(obs.group(2))},
        "sources": [
            {"nom": "Insee, dette trimestrielle des administrations publiques (dernier trimestre)",
             "url": "https://www.insee.fr/fr/statistiques/serie/010777608"},
            {"nom": "Eurostat, dette au sens de Maastricht (gov_10dd_edpt1), 1995 et après",
             "url": "https://ec.europa.eu/eurostat/databrowser/view/gov_10dd_edpt1/default/table?lang=fr"},
            {"nom": "FMI, Global Debt Database, 1978-1994",
             "url": "https://www.imf.org/external/datamapper/GG_DEBT_GDP@GDD/FRA"},
            {"nom": "FMI, Public Finances in Modern History, avant 1978",
             "url": "https://www.imf.org/external/datamapper/d@FPP/FRA"},
        ],
        "note": "Avant 1978, la dette provient d'une reconstitution historique du FMI, aux "
                "définitions différentes : les sauts de 1970 et 1978 sont des changements de "
                "source, pas des hausses réelles. De 1978 à 1994, la Global Debt Database du FMI, "
                "qui raccorde exactement avec la série officielle d'Eurostat utilisée depuis 1995.",
    }


def defense() -> dict:
    import openpyxl

    page = telecharger(URL_SIPRI_PAGE).decode("utf-8", "replace")
    lien = re.search(r'href="([^"]*SIPRI-Milex-data[^"]*\.xlsx)"', page)
    if not lien:
        raise RuntimeError("SIPRI : lien vers le fichier Excel introuvable")
    url = lien.group(1)
    url = "https:" + url if url.startswith("//") else url
    classeur = openpyxl.load_workbook(io.BytesIO(telecharger(url)), read_only=True, data_only=True)

    def feuille(nom: str) -> dict[str, dict[str, float]]:
        """{pays: {année: valeur}} pour une feuille du fichier SIPRI."""
        lignes = list(classeur[nom].iter_rows(values_only=True))
        entete = next(i for i, l in enumerate(lignes) if l and l[0] == "Country")
        colonnes = {j: str(c) for j, c in enumerate(lignes[entete]) if isinstance(c, int)}
        tableau = {}
        for ligne in lignes[entete + 1:]:
            if not ligne or not isinstance(ligne[0], str):
                continue
            valeurs = {colonnes[j]: float(ligne[j]) for j in colonnes
                       if j < len(ligne) and isinstance(ligne[j], (int, float))}
            if valeurs:
                tableau[ligne[0].strip()] = valeurs
        return tableau

    part_pib = feuille("Share of GDP")["France"]
    dollars = {pays: v for pays, v in feuille("Current US$").items()
               if pays != "European Union"}  # ligne d'agrégat, pas un pays
    par_annee: dict[str, dict[str, float]] = {}
    for pays, valeurs in dollars.items():
        for annee, v in valeurs.items():
            par_annee.setdefault(annee, {})[pays] = v
    # Le classement n'a de sens qu'une fois la Chine couverte par SIPRI.
    debut_chine = min(int(a) for a in dollars["China"])
    rang = rangs(par_annee, "France", debut_chine)
    return {
        "titre": "Dépenses militaires",
        "unite": "% du PIB",
        "valeurs": arrondi({a: v * 100 for a, v in part_pib.items()}, 2),
        "rang": rang,
        "rang_libelle": "Rang mondial des dépenses militaires (en dollars courants)",
        "sources": [{"nom": "SIPRI Military Expenditure Database", "url": URL_SIPRI_PAGE}],
        "note": f"Classement calculé sur les pays couverts par le SIPRI, à partir de {min(rang)} "
                "(avant, trop de pays manquent, dont la Chine, pour qu'un rang ait un sens). "
                "Les années où trop de pays n'ont pas publié sont laissées en blanc.",
    }


def recherche() -> dict:
    lignes = oecd_csv(URL_OECD_RD)
    par_annee: dict[str, dict[str, float]] = {}
    for l in lignes:
        zone = l["REF_AREA"]
        if len(zone) == 3 and zone.isalpha() and l["OBS_VALUE"]:  # écarte OCDE, UE27...
            par_annee.setdefault(l["TIME_PERIOD"], {})[zone] = float(l["OBS_VALUE"])
    france = {a: v["FRA"] for a, v in par_annee.items() if "FRA" in v}
    if not france:
        raise RuntimeError("OCDE MSTI : pas de données France")
    ruptures, provisoires = statuts_oecd([l for l in lignes if l["REF_AREA"] == "FRA"])
    rang = rangs(par_annee, "FRA", 1981)
    return {
        "titre": "Recherche et développement",
        "unite": "% du PIB",
        "valeurs": arrondi(france, 2),
        "ruptures": ruptures,
        "provisoires": provisoires,
        "rang": rang,
        "rang_libelle": "Rang de l'effort de R&D (% du PIB) parmi les pays suivis par l'OCDE",
        "sources": [{"nom": "OCDE, Principaux indicateurs de la science et de la technologie (DIRD)",
                     "url": "https://www.oecd.org/fr/data/datasets/main-science-and-technology-indicators.html"}],
        "note": "Dépense intérieure de R&D (publique et privée), série OCDE depuis 1981. "
                f"Classement à partir de {min(rang)}, quand la quarantaine de pays suivis est complète.",
    }


def sante() -> dict:
    lignes = oecd_csv(URL_OECD_SANTE)
    valeurs = {l["TIME_PERIOD"]: float(l["OBS_VALUE"]) for l in lignes if l["OBS_VALUE"]}
    if not valeurs:
        raise RuntimeError("OCDE santé : pas de données France")
    ruptures, provisoires = statuts_oecd(lignes)
    esperance = banque_mondiale_monde("SP.DYN.LE00.IN", population_min=POPULATION_MIN)
    rang = rangs(esperance, "FRA", 1960, garder_valeur=True)
    return {
        "titre": "Dépenses de santé",
        "unite": "% du PIB",
        "valeurs": arrondi(valeurs),
        "ruptures": ruptures,
        "provisoires": provisoires,
        "rang": rang,
        "rang_libelle": "Rang mondial de l'espérance de vie à la naissance",
        "rang_unite": "ans",
        "sources": [{"nom": "OCDE, Statistiques de la santé (système de comptes de la santé)",
                     "url": "https://www.oecd.org/fr/health/health-data.htm"},
                    {"nom": "Banque mondiale, espérance de vie à la naissance (SP.DYN.LE00.IN)",
                     "url": "https://data.worldbank.org/indicator/SP.DYN.LE00.IN"}],
        "note": "Dépense courante de santé, publique et privée, données quinquennales avant 1990. "
                "Aucun classement international fiable n'existe pour les dépenses : le rang porte "
                "sur un résultat, l'espérance de vie, parmi les pays de plus d'un million "
                f"d'habitants (à partir de {min(rang)}, quand la couverture mondiale est complète).",
    }


def education() -> dict:
    # Banque mondiale avant 1995 (elle a un trou de 1999 à 2016), Eurostat ensuite.
    valeurs = {x["date"]: x["value"] for x in banque_mondiale("FRA", "SE.XPD.TOTL.GD.ZS")
               if int(x["date"]) < 1995}
    cofog = eurostat(URL_EUROSTAT_EDUCATION)
    if "2010" not in cofog:
        raise RuntimeError("Eurostat : série éducation incomplète")
    valeurs.update(cofog)
    return {
        "titre": "Dépenses publiques d'éducation",
        "unite": "% du PIB",
        "valeurs": arrondi(valeurs),
        "ruptures": [1995],
        "pisa": PISA,
        "sources": [
            {"nom": "Eurostat, dépenses des administrations publiques par fonction (gov_10a_exp, "
                    "éducation), 1995 et après",
             "url": "https://ec.europa.eu/eurostat/databrowser/view/gov_10a_exp/default/table?lang=fr"},
            {"nom": "Banque mondiale / UNESCO (SE.XPD.TOTL.GD.ZS), avant 1995",
             "url": "https://data.worldbank.org/indicator/SE.XPD.TOTL.GD.ZS?locations=FR"},
            {"nom": "OCDE, PISA (2000-2022) ; DEPP, note d'information 26.40 (PISA 2025)",
             "url": "https://www.oecd.org/fr/about/programmes/pisa.html"},
        ],
        "note": "Dépense publique uniquement (les familles et entreprises financent aussi "
                "l'éducation). Deux sources aux définitions proches mais distinctes : UNESCO / "
                "Banque mondiale avant 1995, Eurostat ensuite ; la série d'avant 1995 comporte "
                "elle-même des sauts (1974, 1993) à interpréter avec prudence. PISA évalue les "
                "élèves de 15 ans tous les 3 ans depuis 2000.",
    }


def economie() -> dict:
    croissance = banque_mondiale("FRA", "NY.GDP.MKTP.KD.ZG")
    par_annee = banque_mondiale_monde("NY.GDP.MKTP.CD", population_min=POPULATION_MIN)
    return {
        "titre": "Croissance économique",
        "unite": "% par an",
        "valeurs": arrondi({x["date"]: x["value"] for x in croissance}),
        "rang": rangs(par_annee, "FRA", 1992),
        "rang_libelle": "Rang mondial du PIB (en dollars courants)",
        "sources": [{"nom": "Banque mondiale (NY.GDP.MKTP.KD.ZG et NY.GDP.MKTP.CD)",
                     "url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD"}],
        "note": "Classement parmi les pays de plus d'un million d'habitants, à partir de 1992 : "
                "avant, l'URSS est absente des données de la Banque mondiale, ce qui fausserait "
                "le rang de la France.",
    }


# --- Image de partage (réseaux sociaux) ------------------------------------------------


def dessiner_dette(serie: dict, chemin: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Dette = encours au 31 décembre : on place le point au tout début de l'année suivante,
    # pour que chaque mandat parte du niveau dont il hérite.
    annees = [int(a) + 1 for a in serie["valeurs"]]
    valeurs = list(serie["valeurs"].values())
    fig, ax = plt.subplots(figsize=(12, 6.3), dpi=100)
    for i, p in enumerate(PRESIDENCES):
        fin = min(p["fin"], max(annees))
        ax.axvspan(p["debut"], fin, color="#14387f" if i % 2 else "#e1000f", alpha=0.06, lw=0)
        ax.text((p["debut"] + fin) / 2, 4, p["court"], ha="center", fontsize=10, color="#1b2b4f")
    ax.plot(annees, valeurs, color="#14387f", lw=3)
    ax.set_xlim(1959, max(annees))
    ax.set_ylim(0, max(valeurs) * 1.12)
    ax.set_ylabel("% du PIB")
    ax.set_title("Dette publique de la France par présidence (% du PIB)",
                 fontsize=16, color="#14387f", loc="left")
    ax.annotate(f"{valeurs[-1]:.1f} %".replace(".", ","), (annees[-1], valeurs[-1]),
                textcoords="offset points", xytext=(-60, 8), fontsize=12, color="#e1000f")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#dbe2ef")
    fig.text(0.01, 0.01, "Sources : FMI (avant 1995), Eurostat/Insee (depuis 1995)",
             fontsize=9, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(chemin)
    plt.close(fig)


def main() -> int:
    collecteurs = {"dette": dette, "sante": sante, "education": education,
                   "defense": defense, "recherche": recherche, "economie": economie}
    series = {}
    for cle, fonction in collecteurs.items():
        try:
            series[cle] = fonction()
        except Exception as e:  # noqa: BLE001 - on signale la source fautive puis on arrête
            print(f"ERREUR {cle} : {e}", file=sys.stderr)
            return 1
        derniere = max(series[cle]["valeurs"])
        print(f"{cle:10} {len(series[cle]['valeurs']):3} années, dernière {derniere}")

    # « mise_a_jour » ne change que si les chiffres changent ; « verification » change à
    # chaque passage, ce qui garde aussi le dépôt actif (GitHub suspend les tâches
    # planifiées d'un dépôt sans activité depuis 60 jours).
    mise_a_jour = date.today().isoformat()
    ancien = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    inchange = ancien.get("series") == series and ancien.get("presidences") == PRESIDENCES
    if inchange:
        mise_a_jour = ancien["mise_a_jour"]
        print("Aucune donnée nouvelle.")
    if not inchange or not IMAGE_DETTE.exists():
        dessiner_dette(series["dette"], IMAGE_DETTE)  # avant le JSON : un échec n'écrit rien

    donnees = {"mise_a_jour": mise_a_jour, "verification": date.today().isoformat(),
               "presidences": PRESIDENCES, "series": series}
    SORTIE.parent.mkdir(exist_ok=True)
    SORTIE.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Écrit : {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
