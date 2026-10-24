// Outils communs : chargement de data/donnees.json, bilans par mandat et graphiques Chart.js.
// Les données sont produites par scripts/maj_donnees.py : ne rien saisir à la main ici.
const FES = (() => {
  const BLEU = "#14387f";
  const ROUGE = "#e1000f";
  const ORANGE = "#c96a00";

  // La dette est un encours au 31 décembre : on la place au début de l'année suivante.
  // Les autres séries sont des flux annuels : on les place au milieu de l'année.
  const DECALAGE = { dette: 1 };

  async function charger() {
    const rep = await fetch("data/donnees.json", { cache: "no-cache" });
    if (!rep.ok) throw new Error(`données indisponibles (HTTP ${rep.status})`);
    return rep.json();
  }

  function nombre(v, decimales = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return "n.d.";
    return v.toLocaleString("fr-FR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
  }

  function ecart(v, decimales = 1) {
    const signe = v > 0 ? "+" : v < 0 ? "−" : "";
    return signe + nombre(Math.abs(v), decimales);
  }

  // 1 -> "1er", 7 -> "7e"
  function ordinal(n) {
    return n === 1 ? "1er" : `${n}e`;
  }

  function dateFr(iso) {
    return new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
  }

  function annees(valeurs) {
    return Object.keys(valeurs).map(Number).sort((a, b) => a - b);
  }

  // Valeur de l'année demandée, sinon de l'année la plus proche (à `marge` ans près),
  // sans sortir de l'intervalle [min, max].
  function valeurProche(valeurs, annee, marge = 2, min = -Infinity, max = Infinity) {
    for (let d = 0; d <= marge; d++) {
      for (const a of [annee - d, annee + d]) {
        if (a >= min && a <= max && valeurs[a] !== undefined) return { annee: a, valeur: valeurs[a] };
      }
    }
    return null;
  }

  // Bilan d'un mandat : niveau hérité (fin de l'année précédant l'entrée en fonction)
  // et niveau laissé (fin de l'année précédant le départ, ou dernière donnée connue).
  // Pour les séries à trous, on tolère une année voisine (le niveau hérité peut être lu
  // jusqu'à l'année d'arrivée incluse), mais jamais hors du mandat. `rupture` signale un
  // changement de source entre les deux années comparées.
  function bilan(valeurs, p, ruptures = []) {
    const liste = annees(valeurs);
    const anneeFin = Math.min(p.fin - 1, liste[liste.length - 1]);
    const debut = valeurProche(valeurs, p.debut - 1, 2, -Infinity, p.debut + 1);
    const fin = valeurProche(valeurs, anneeFin, 2, p.debut, anneeFin);
    if (!debut || !fin || fin.annee <= debut.annee) return null;
    const variation = fin.valeur - debut.valeur;
    const rupture = ruptures.some(r => r > debut.annee && r <= fin.annee);
    return { debut, fin, variation, rupture, parAn: variation / (fin.annee - debut.annee) };
  }

  // Moyenne des valeurs annuelles pendant le mandat (pour la croissance).
  function moyenne(valeurs, p) {
    const retenues = annees(valeurs).filter(a => a >= p.debut && a < p.fin);
    if (!retenues.length) return null;
    const somme = retenues.reduce((s, a) => s + valeurs[a], 0);
    return { valeur: somme / retenues.length, de: retenues[0], a: retenues[retenues.length - 1] };
  }

  function points(valeurs, decalage, transformer = v => v) {
    return annees(valeurs).map(a => ({ x: a + decalage, y: transformer(valeurs[a]), annee: a, brut: valeurs[a] }));
  }

  // Rangs avec des trous : les années non classées restent vides au lieu d'être reliées.
  function pointsRang(rang, decalage) {
    const liste = annees(rang);
    const data = [];
    for (let a = liste[0]; a <= liste[liste.length - 1]; a++) {
      const r = rang[a];
      data.push(r ? { x: a + decalage, y: r[0], annee: a, sur: r[1], mesure: r[2] } : { x: a + decalage, y: null });
    }
    return data;
  }

  // Trait vertical discret aux ruptures de série (changement de source ou de méthode).
  function pluginRuptures(ruptures, decalage) {
    return {
      id: "ruptures",
      afterDatasetsDraw(chart) {
        const { ctx, chartArea: zone, scales: { x } } = chart;
        ctx.save();
        ctx.strokeStyle = "#8a93a6";
        ctx.fillStyle = "#5a6478";
        ctx.setLineDash([3, 3]);
        ctx.font = "10px system-ui, sans-serif";
        ctx.textAlign = "center";
        for (const r of ruptures) {
          const px = x.getPixelForValue(r + decalage - 0.5);
          if (px < zone.left || px > zone.right) continue;
          ctx.beginPath();
          ctx.moveTo(px, zone.top + 12);
          ctx.lineTo(px, zone.bottom);
          ctx.stroke();
          ctx.fillText("rupture", px, zone.top + 9);
        }
        ctx.restore();
      },
    };
  }

  // Bandes colorées et noms des présidents en fond de graphique.
  function pluginBandes(presidences) {
    return {
      id: "bandes",
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea: zone, scales: { x } } = chart;
        ctx.save();
        ctx.font = "11px system-ui, sans-serif";
        ctx.textAlign = "center";
        presidences.forEach((p, i) => {
          const gauche = Math.max(x.getPixelForValue(p.debut), zone.left);
          const droite = Math.min(x.getPixelForValue(p.fin), zone.right);
          if (droite <= gauche) return;
          ctx.fillStyle = i % 2 ? "rgba(20,56,127,0.07)" : "rgba(225,0,15,0.05)";
          ctx.fillRect(gauche, zone.top, droite - gauche, zone.bottom - zone.top);
          if (ctx.measureText(p.court).width < droite - gauche - 4) {
            ctx.fillStyle = "#1b2b4f";
            ctx.fillText(p.court, (gauche + droite) / 2, zone.bottom - 6);
          }
        });
        ctx.restore();
      },
    };
  }

  function axeX(donnees, cles) {
    const fin = Math.max(...cles.map(c => Math.max(...annees(donnees.series[c].valeurs)) + 1));
    return {
      type: "linear",
      min: 1959,
      max: fin,
      ticks: { stepSize: 5, callback: v => (Number.isInteger(v) ? String(v) : "") },
      grid: { color: "#eef2f8" },
    };
  }

  function ligne(label, data, couleur, axe, extra = {}) {
    return {
      label, data, yAxisID: axe,
      borderColor: couleur, backgroundColor: couleur,
      borderWidth: 2.5, pointRadius: 0, pointHoverRadius: 4,
      cubicInterpolationMode: "monotone",  // courbe adoucie sans dépasser les valeurs réelles
      ...extra,
    };
  }

  // Première année classée d'une série (ou null si elle n'a pas de rang).
  function debutClassement(s) {
    return s.rang ? annees(s.rang)[0] : null;
  }

  // Graphique d'un domaine : la série en % (axe gauche) et, s'il existe, le rang
  // mondial ou le score PISA (axe droit). Avec `periodeClassee`, le graphique se limite
  // aux années où le rang mondial existe et l'axe gauche se resserre sur les valeurs.
  // `depuisDebut` cale l'axe des années sur le début de la série au lieu de 1959.
  function graphique(canvas, donnees, cle, { periodeClassee = false, depuisDebut = false } = {}) {
    const s = donnees.series[cle];
    const decalage = DECALAGE[cle] ?? 0.5;
    const debut = periodeClassee ? debutClassement(s) : null;
    const valeurs = debut
      ? Object.fromEntries(Object.entries(s.valeurs).filter(([a]) => Number(a) >= debut))
      : s.valeurs;
    const jeux = [ligne(`${s.titre} (${s.unite})`, points(valeurs, decalage), BLEU, "y")];
    const x = axeX(donnees, [cle]);
    if (debut) x.min = debut;
    else if (depuisDebut) x.min = Math.min(annees(s.valeurs)[0], debutClassement(s) ?? Infinity);
    const echelles = {
      x,
      y: {
        position: "left",
        // Pas de zéro pour les indices qui varient peu (IDH entre 0,8 et 0,92, par exemple).
        beginAtZero: !debut && cle !== "economie" && s.axe_zero !== false,
        title: { display: true, text: s.unite, color: BLEU },
        ticks: { color: BLEU, callback: v => nombre(v, Number.isInteger(v) ? 0 : Math.max(1, Math.min(s.decimales ?? 1, 2))) },
        // Ligne du zéro appuyée : on voit tout de suite quand la croissance est négative.
        grid: { color: c => (c.tick.value === 0 ? "#8a93a6" : "#eef2f8"), lineWidth: c => (c.tick.value === 0 ? 1.5 : 1) },
      },
    };

    // L'axe de droite est resserré sur les valeurs observées pour que la courbe occupe
    // toute la hauteur ; les graduations et l'infobulle donnent l'échelle réelle.
    if (s.rang) {
      // Petits points : un rang isolé entre deux années non classées reste visible.
      jeux.push(ligne(s.rang_libelle, pointsRang(s.rang, 0.5), ROUGE, "y1", { pointRadius: 2 }));
      const valeurs = Object.values(s.rang).map(r => r[0]);
      echelles.y1 = {
        position: "right",
        reverse: true,
        min: Math.max(0.5, Math.min(...valeurs) - 0.5),
        max: Math.max(...valeurs) + 0.5,
        title: { display: true, text: "Rang (1 = premier)", color: ROUGE },
        ticks: { color: ROUGE, autoSkip: true, callback: v => ordinal(v) },
        // Les bornes sont des demi-rangs : on impose des graduations sur les rangs entiers.
        afterBuildTicks: axe => {
          const graduations = [];
          for (let v = Math.ceil(axe.min); v <= Math.floor(axe.max); v++) graduations.push({ value: v });
          axe.ticks = graduations;
        },
        grid: { drawOnChartArea: false },
      };
    }

    if (s.pisa) {
      const pisa = { maths: ["PISA mathématiques (score)", ROUGE], lecture: ["PISA compréhension de l'écrit (score)", ORANGE] };
      for (const [domaine, [label, couleur]] of Object.entries(pisa)) {
        jeux.push(ligne(label, points(s.pisa[domaine], 0.4), couleur, "y1", { pointRadius: 3 }));
      }
      const scores = [...Object.values(s.pisa.maths), ...Object.values(s.pisa.lecture)];
      echelles.y1 = {
        position: "right",
        min: Math.floor((Math.min(...scores) - 5) / 10) * 10,
        max: Math.ceil((Math.max(...scores) + 5) / 10) * 10,
        title: { display: true, text: "Score PISA", color: ROUGE },
        ticks: { color: ROUGE, precision: 0 },
        grid: { drawOnChartArea: false },
      };
    }

    return new Chart(canvas, {
      type: "line",
      data: { datasets: jeux },
      plugins: [pluginBandes(donnees.presidences), pluginRuptures(s.ruptures || [], decalage)],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: echelles,
        plugins: {
          legend: { position: "top", labels: { boxWidth: 18 } },
          tooltip: {
            callbacks: {
              title: items => String(items[0].raw.annee),
              label: item => {
                const pt = item.raw;
                if (pt.sur) {
                  const mesure = s.rang_unite ? ` (${nombre(pt.mesure)} ${s.rang_unite})` : "";
                  return ` ${ordinal(pt.y)} sur ${pt.sur} pays${mesure}`;
                }
                if (item.dataset.yAxisID === "y1") return ` ${item.dataset.label} : ${pt.y}`;
                const dec = s.decimales ?? (Number.isInteger(Math.round(pt.y * 100) / 10) ? 1 : 2);
                return ` ${nombre(pt.y, dec)} ${s.unite}`;
              },
            },
          },
        },
      },
    });
  }

  // Liste des sources d'une série (liens) et date de mise à jour.
  function sourcesHtml(s) {
    return s.sources.map(src => `<a href="${src.url}" target="_blank" rel="noopener">${src.nom}</a>`).join(" ; ");
  }

  function afficherMiseAJour(donnees) {
    document.querySelectorAll("[data-maj]").forEach(el => { el.textContent = dateFr(donnees.mise_a_jour); });
    document.querySelectorAll("[data-verification]").forEach(el => { el.textContent = dateFr(donnees.verification); });
  }

  function signalerErreur(el, erreur) {
    el.innerHTML = `<p class="erreur-donnees">Impossible de charger les données : ${erreur.message}.</p>`;
  }

  // Phrase sur les valeurs provisoires d'une série, ou chaîne vide.
  function provisoires(s) {
    if (!s.provisoires || !s.provisoires.length) return "";
    return ` Valeur${s.provisoires.length > 1 ? "s" : ""} provisoire${s.provisoires.length > 1 ? "s" : ""} : ${s.provisoires.join(", ")}.`;
  }

  return { charger, nombre, ecart, ordinal, provisoires, debutClassement, bilan, moyenne, valeurProche, annees, graphique, sourcesHtml, afficherMiseAJour, signalerErreur };
})();
