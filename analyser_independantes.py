"""Comptage + analyse des agences indépendantes, avec la répartition par effectif.

Usage : python analyser_independantes.py                       (agences_independantes.csv)
        python analyser_independantes.py mon_fichier.csv

Lit agences_independantes.csv (produit par compter_agences.py --filtrer, puis enrichi par
recuperer_effectifs.py) et écrit :
  effectifs_repartition.csv             nombre d'agences par tranche d'effectif
  reseaux_candidats_independantes.csv   motifs d'enseigne qui se répètent
Si reseaux.txt existe, les réseaux connus sont aussi cherchés (enseigne et nom).
Si les colonnes d'effectif sont absentes, la partie 6 est ignorée : lancer d'abord
recuperer_effectifs.py.
"""
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

# tranches d'effectif INSEE, dans l'ordre croissant
TRANCHES = [
    ("NN", "Non employeuse"), ("00", "0 salarié"), ("01", "1 à 2 salariés"),
    ("02", "3 à 5 salariés"), ("03", "6 à 9 salariés"), ("11", "10 à 19 salariés"),
    ("12", "20 à 49 salariés"), ("21", "50 à 99 salariés"), ("22", "100 à 199 salariés"),
    ("31", "200 à 249 salariés"), ("32", "250 à 499 salariés"), ("41", "500 à 999 salariés"),
    ("42", "1 000 à 1 999 salariés"), ("51", "2 000 à 4 999 salariés"),
    ("52", "5 000 à 9 999 salariés"), ("53", "10 000 salariés et plus"),
]
LIBELLES = dict(TRANCHES)
ORDRE = {code: i for i, (code, _) in enumerate(TRANCHES)}
GROUPES = [
    ("Sans salarié", {"NN", "00"}),
    ("1 à 9 salariés", {"01", "02", "03"}),
    ("10 à 49 salariés", {"11", "12"}),
    ("50 à 249 salariés", {"21", "22", "31"}),
    ("250 salariés et plus", {"32", "41", "42", "51", "52", "53"}),
]
FORMES = {"sarl", "sas", "sasu", "eurl", "sa", "snc", "sci", "selarl", "sc", "ei",
          "eirl", "ste", "societe", "scp"}
GENERIQUES = {"agence", "agences", "cabinet", "groupe", "immobilier", "immobiliere",
              "immobiliers", "immo", "le", "la", "les", "l", "de", "du", "des", "d",
              "et", "en", "a", "au", "aux", "the", "mr", "mme", "m"}
JURIDIQUES = {"1000": "Entrepreneur individuel", "5498": "EURL", "5499": "SARL",
              "5599": "SA", "5710": "SAS", "5720": "SASU", "6540": "SCI",
              "5202": "SNC", "6599": "Autre société civile"}


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def marque(texte):
    """Premier mot significatif (sans forme juridique ni mot générique)."""
    if "non diffusible" in normaliser(texte):
        return ""
    for mot in normaliser(texte).split():
        if mot not in FORMES and mot not in GENERIQUES and len(mot) > 1:
            return mot
    return ""


def valides(gerants):
    """(texte d'origine, clé) des gérants exploitables : ni masqués ni commissaires aux comptes."""
    for part in (gerants or "").split(" | "):
        m = re.search(r"\(([^)]*)\)\s*$", part)
        qualite = m.group(1).lower() if m else ""
        nom = re.sub(r"\s*\([^)]*\)\s*$", "", part).strip()
        if not nom or "non-diffusible" in nom.lower() or "commissaire" in qualite:
            continue
        yield part.strip(), normaliser(nom)


def masque(l):
    return (l.get("code_postal") or "").startswith("[") or (l.get("adresse") or "").startswith("[")


def departement(cp):
    cp = (cp or "").strip()
    if not re.fullmatch(r"\d{5}", cp):
        return "?"
    if cp.startswith("20"):
        return "2A" if int(cp) < 20200 else "2B"
    if cp.startswith(("97", "98")):
        return cp[:3]
    return cp[:2]


def code_effectif(l):
    """Code de tranche normalisé ('1' devient '01' si Excel a retiré le zéro)."""
    code = (l.get("effectif_code") or "").strip().upper()
    if code.isdigit() and len(code) == 1:
        code = code.zfill(2)
    return code


def pct(a, b):
    return f"{a / b:.1%}" if b else "0%"


def barre(n, maxi, largeur=20):
    return "█" * round(n / maxi * largeur) if maxi else ""


def main():
    fichier = next((a for a in sys.argv[1:] if not a.startswith("--")), "agences_independantes.csv")
    if not os.path.exists(fichier):
        sys.exit(f"Fichier introuvable : {fichier}")
    with open(fichier, newline="", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        champs = lecteur.fieldnames or []
        lignes = list(lecteur)
    nb = len(lignes)
    if not nb:
        sys.exit("Fichier vide.")

    # ---------- 1. comptage ----------
    print("1. COMPTAGE")
    par_dep = Counter(departement(l.get("code_postal")) for l in lignes)
    codes = sorted(par_dep)
    for i in range(0, len(codes), 4):
        print("  ".join(f"{d:>3}:{par_dep[d]:>5}" for d in codes[i:i + 4]))
    print(f"Départements : {len([d for d in par_dep if d != '?'])}"
          + (f" (+ {par_dep['?']} sans code postal exploitable)" if par_dep.get("?") else ""))
    sirens = Counter((l.get("siren") or "").strip() for l in lignes)
    print(f"Agences indépendantes : {nb}   SIREN distincts : {len(sirens)}")

    # ---------- 2. structure ----------
    print("\n2. STRUCTURE D'UNE AGENCE")
    exemple = max(lignes, key=lambda l: sum(1 for c in champs if (l.get(c) or "").strip()))
    for c in champs:
        v = (exemple.get(c) or "").strip() or "(vide)"
        print(f"  {c:<17}: {v}")
    print("  (exemple : la ligne la plus complète)")
    print("Champs vides :")
    for c in champs:
        if c in ("source", "date_collecte") or c.startswith("lien_"):
            continue
        vide = sum(1 for l in lignes if not (l.get(c) or "").strip())
        print(f"  {c:<17}{vide:>7}  ({pct(vide, nb)})")
    problemes = []
    mauvais_siren = sum(1 for l in lignes if not re.fullmatch(r"\d{9}", (l.get("siren") or "").strip()))
    mauvais_siret = sum(1 for l in lignes
                        if not (re.fullmatch(r"\d{14}", (l.get("siret_siege") or "").strip())
                                and (l.get("siret_siege") or "").startswith((l.get("siren") or "").strip())))
    if mauvais_siren:
        problemes.append(f"{mauvais_siren} SIREN invalides")
    if mauvais_siret:
        problemes.append(f"{mauvais_siret} SIRET invalides")
    print("Problèmes : " + ("; ".join(problemes) if problemes else "aucun"))
    print(f"Info : {sum(1 for l in lignes if masque(l))} agences ont une adresse masquée "
          "[NON-DIFFUSIBLE] (pas une erreur)")

    # ---------- 3. doublons et gérants ----------
    print("\n3. DOUBLONS ET GÉRANTS")
    print(f"Par SIREN : {nb - len(sirens)} lignes en trop")
    sirets = Counter((l.get("siret_siege") or "").strip() for l in lignes)
    print(f"Par SIRET (siège) : {nb - len(sirets)} lignes en trop")
    gerant_soc = defaultdict(set)
    for l in lignes:
        for _, cle in valides(l.get("gerants")):
            gerant_soc[cle].add(l["siren"])
    print(f"Gérants distincts : {len(gerant_soc)}")
    for s in (2, 5, 10, 20):
        g = [len(v) for v in gerant_soc.values() if len(v) >= s]
        print(f"  dans {s} agences ou plus : {len(g)} gérants ({sum(g)} agences)")
    adr = defaultdict(set)
    for l in lignes:
        if not masque(l) and (l.get("adresse") or "").strip():
            adr[normaliser(l["adresse"])].add(l["siren"])
    partagees = [len(v) for v in adr.values() if len(v) >= 2]
    print(f"Même adresse pour 2 agences ou plus : {len(partagees)} adresses ({sum(partagees)} agences)")
    sans_gerant = sum(1 for l in lignes if not list(valides(l.get("gerants"))))
    print(f"Sans gérant exploitable : {sans_gerant} ({pct(sans_gerant, nb)})")

    # ---------- 4. nature juridique ----------
    print("\n4. NATURE JURIDIQUE")
    if "nature_juridique" in champs:
        nj = Counter((l.get("nature_juridique") or "").strip() for l in lignes)
        for code, n in nj.most_common(8):
            print(f"  {code or '(vide)':<6} {JURIDIQUES.get(code, ''):<24} {n:>6}  ({pct(n, nb)})")
    else:
        print("Colonne nature_juridique absente.")

    # ---------- 5. réseaux ----------
    print("\n5. RÉSEAUX (enseigne et nom)")
    avec_ens = [l for l in lignes if (l.get("enseigne") or "").strip()]
    ens_distinctes = {normaliser(e) for l in avec_ens for e in l["enseigne"].split(" | ") if e.strip()}
    print(f"Agences avec une enseigne : {len(avec_ens)} ({pct(len(avec_ens), nb)}), "
          f"{len(ens_distinctes)} enseignes distinctes")

    g = defaultdict(list)
    for l in lignes:
        for m in {marque(e) for e in (l.get("enseigne") or "").split(" | ") if e.strip()}:
            if m:
                g[m].append(l)
    gros = sorted(((m, ls) for m, ls in g.items() if len(ls) >= 5), key=lambda x: -len(x[1]))
    print(f"Motifs d'ENSEIGNE sur 5 agences ou plus : {len(gros)} ({sum(len(x) for _, x in gros)} agences)")
    for m, ls in gros[:10]:
        print(f"  {m} : {len(ls)}")
    with open("reseaux_candidats_independantes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["motif", "nb_agences", "exemples"])
        for m, ls in gros:
            ex = " / ".join((x.get("enseigne") or "")[:30] for x in ls[:2])
            w.writerow([m, len(ls), ex])

    connus = []
    if os.path.exists("reseaux.txt"):
        with open("reseaux.txt", encoding="utf-8") as f:
            connus = [(n.split("#")[0].strip(), normaliser(n.split("#")[0])) for n in f
                      if normaliser(n.split("#")[0])]
    soc_reseau = set()
    trouves = Counter()
    for l in lignes:
        en = " " + normaliser(l.get("enseigne")) + " "
        ec = en.replace(" ", "")
        nm = " " + normaliser(l.get("nom")) + " "
        for nom_r, cle in connus:
            if f" {cle} " in en or ec == cle.replace(" ", "") or f" {cle} " in nm:
                trouves[nom_r] += 1
                soc_reseau.add(l["siren"])
    if connus:
        print(f"Réseaux de reseaux.txt trouvés : {len(trouves)} sur {len(connus)} "
              f"({len(soc_reseau)} agences)")
        for n, c in trouves.most_common(10):
            print(f"  {n} : {c}")
    else:
        print("reseaux.txt absent : réseaux connus non cherchés")

    def a_reseau(l):
        return bool((l.get("enseigne") or "").strip()) or l["siren"] in soc_reseau

    sans_reseau = [l for l in lignes if not a_reseau(l)]
    print(f"Sans enseigne et sans réseau connu : {len(sans_reseau)} ({pct(len(sans_reseau), nb)})")
    print(f"Avec enseigne ou réseau connu      : {nb - len(sans_reseau)} "
          f"({pct(nb - len(sans_reseau), nb)})")

    # ---------- 6. effectifs ----------
    print("\n6. EFFECTIFS")
    if "effectif_code" not in champs:
        print("Colonnes d'effectif absentes : lancer d'abord recuperer_effectifs.py.")
    else:
        statuts = Counter((l.get("effectif_statut") or "non traité") for l in lignes)
        print("Statut de la récupération :")
        for s, n in statuts.most_common():
            print(f"  {s:<14}{n:>7}  ({pct(n, nb)})")

        par_code = Counter()
        non_renseigne = 0
        for l in lignes:
            if (l.get("effectif_statut") or "") != "ok":
                continue
            code = code_effectif(l)
            if code in LIBELLES:
                par_code[code] += 1
            else:
                non_renseigne += 1
        connus_n = sum(par_code.values())
        print(f"\nAgences avec une tranche d'effectif : {connus_n} ({pct(connus_n, nb)})")
        print(f"Interrogées mais effectif non renseigné par l'INSEE : {non_renseigne}")
        a_traiter = nb - connus_n - non_renseigne
        print(f"Introuvables, en erreur ou non traitées : {a_traiter}")

        print("\nNombre d'agences par tranche d'effectif (parmi celles avec une tranche) :")
        maxi = max(par_code.values()) if par_code else 0
        lignes_csv = []
        for code, libelle in TRANCHES:
            n = par_code.get(code, 0)
            if not n:
                continue
            print(f"  {libelle:<26}{n:>7}  {pct(n, connus_n):>6}  {barre(n, maxi)}")
            lignes_csv.append([code, libelle, n, f"{n / connus_n:.4f}"])
        if non_renseigne:
            lignes_csv.append(["", "Effectif non renseigné", non_renseigne, ""])
        with open("effectifs_repartition.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code", "tranche", "nb_agences", "part"])
            w.writerows(lignes_csv)

        print("\nPar grandes catégories :")
        for nom, codes_g in GROUPES:
            n = sum(par_code.get(c, 0) for c in codes_g)
            if n:
                print(f"  {nom:<26}{n:>7}  {pct(n, connus_n):>6}")
        avec_sal = sum(n for c, n in par_code.items() if c not in ("NN", "00"))
        dix_plus = sum(n for c, n in par_code.items() if ORDRE[c] >= ORDRE["11"])
        print(f"\nAu moins 1 salarié : {avec_sal} ({pct(avec_sal, connus_n)})")
        print(f"10 salariés ou plus : {dix_plus} ({pct(dix_plus, connus_n)})")

        annees = Counter((l.get("effectif_annee") or "").strip() for l in lignes
                         if (l.get("effectif_statut") or "") == "ok")
        if annees:
            print("\nAnnée de la donnée d'effectif :")
            for a, n in sorted(annees.items(), reverse=True):
                print(f"  {a or '(vide)':<8}{n:>7}")

        if "effectif_siege" in champs:
            sieges = Counter((l.get("effectif_siege") or "").strip() for l in lignes
                             if (l.get("effectif_statut") or "") == "ok")
            renseignes = sum(n for s, n in sieges.items() if s)
            print(f"\nEffectif du siège renseigné pour {renseignes} agences "
                  f"({pct(renseignes, connus_n)})")
            for libelle in [lib for _, lib in TRANCHES]:
                if sieges.get(libelle):
                    print(f"  {libelle:<26}{sieges[libelle]:>7}")

        print("\nEffectif selon l'enseigne ou le réseau :")
        print(f"  {'':<22}{'avec enseigne/réseau':>22}{'sans':>8}")
        for nom, codes_g in GROUPES:
            av = sum(1 for l in lignes if (l.get("effectif_statut") or "") == "ok"
                     and code_effectif(l) in codes_g and a_reseau(l))
            sa = sum(1 for l in lignes if (l.get("effectif_statut") or "") == "ok"
                     and code_effectif(l) in codes_g and not a_reseau(l))
            if av or sa:
                print(f"  {nom:<22}{av:>22}{sa:>8}")

    print("\nFichiers écrits : effectifs_repartition.csv, reseaux_candidats_independantes.csv")


if __name__ == "__main__":
    main()
