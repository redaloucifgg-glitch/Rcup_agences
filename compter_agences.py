"""Comptage + vérification + dédoublonnage + repérage des réseaux.

Usage : python compter_agences.py                    (dossier data/)
        python compter_agences.py --filtrer          (+ retire sans gérant et gérants trop gros)
        python compter_agences.py --filtrer --seuil 10
        python compter_agences.py mon_dossier

Lit data/agences_*.csv et écrit :
  agences_uniques.csv     une ligne par SIREN (avec --filtrer : sans gérant exploitable
                          et gérants dans SEUIL sociétés ou plus retirés, 5 par défaut)
  reseaux_candidats.csv   motifs d'enseigne / de nom qui se répètent (réseaux possibles)
Si reseaux.txt existe, les réseaux connus sont aussi cherchés (enseigne et nom).
"""
import csv
import glob
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

DEPARTEMENTS = (
    [f"{i:02d}" for i in range(1, 96) if i != 20]
    + ["2A", "2B", "971", "972", "973", "974", "976"]
)
BASE = ["siren", "siret_siege", "nom", "enseigne", "adresse", "code_postal",
        "ville", "date_creation", "gerants", "source", "date_collecte"]
OPTIONNELLES = ["nature_juridique"]
FORMES = {"sarl", "sas", "sasu", "eurl", "sa", "snc", "sci", "selarl", "sc", "ei",
          "eirl", "ste", "societe", "sasu", "scp"}
GENERIQUES = {"agence", "agences", "cabinet", "groupe", "immobilier", "immobiliere",
              "immobiliers", "immo", "le", "la", "les", "l", "de", "du", "des", "d",
              "et", "en", "a", "au", "aux", "the", "mr", "mme", "m"}
JURIDIQUES = {"1000": "Entrepreneur individuel", "5498": "EURL", "5499": "SARL",
              "5599": "SA", "5710": "SAS", "5720": "SASU", "6540": "SCI",
              "5202": "SNC", "5307": "SA (société en nom collectif)"}


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def marque(texte):
    """Premier mot significatif (sans forme juridique ni mot générique)."""
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


def cp_coherent(cp, dep):
    if not cp or cp.startswith("["):
        return True
    if dep in ("2A", "2B"):
        return cp.startswith("20")
    return cp.startswith(dep)


def masque(l):
    return (l.get("code_postal") or "").startswith("[") or (l.get("adresse") or "").startswith("[")


def pct(a, b):
    return f"{a / b:.0%}" if b else "0%"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    filtrer = "--filtrer" in sys.argv
    seuil = 5
    if "--seuil" in sys.argv:
        seuil = int(sys.argv[sys.argv.index("--seuil") + 1])
        args = [a for a in args if a != str(seuil)]
    dossier = args[0] if args else "data"
    fichiers = sorted(glob.glob(os.path.join(dossier, "agences_*.csv")))
    if not fichiers:
        sys.exit(f"Aucun fichier agences_*.csv dans {dossier}/")

    # ---------- lecture ----------
    par_dep, colonnes_ko = {}, []
    uniques = {}                      # siren -> ligne (première vue, adresse non masquée si possible)
    doublons_siren, sirets, doublons_siret = [], {}, 0
    mauvais_siren = mauvais_siret = cp_ko = 0
    exemples_cp, vides = [], Counter()
    exemple, exemple_dep, exemple_score = None, "", -1
    total, champs = 0, None

    for chemin in fichiers:
        dep = os.path.basename(chemin)[len("agences_"):-len(".csv")]
        n = 0
        with open(chemin, newline="", encoding="utf-8") as f:
            lecteur = csv.DictReader(f)
            ent = lecteur.fieldnames or []
            champs = champs or ent
            attendu = BASE + [c for c in OPTIONNELLES if c in ent]
            if sorted(ent) != sorted(attendu):
                colonnes_ko.append(dep)
            for l in lecteur:
                n += 1
                siren = (l.get("siren") or "").strip()
                siret = (l.get("siret_siege") or "").strip()
                if not re.fullmatch(r"\d{9}", siren):
                    mauvais_siren += 1
                if not (re.fullmatch(r"\d{14}", siret) and siret.startswith(siren)):
                    mauvais_siret += 1
                if siret in sirets:
                    doublons_siret += 1
                sirets[siret] = dep
                for c in ent:
                    if not (l.get(c) or "").strip():
                        vides[c] += 1
                score = sum(1 for c in ent if (l.get(c) or "").strip())
                if score > exemple_score:
                    exemple, exemple_dep, exemple_score = dict(l), dep, score
                if not cp_coherent((l.get("code_postal") or "").strip(), dep):
                    cp_ko += 1
                    if len(exemples_cp) < 3:
                        exemples_cp.append(f"{siren} ({dep}, cp {l.get('code_postal')})")
                if siren in uniques:
                    doublons_siren.append((siren, uniques[siren]["_dep"], dep))
                    if masque(uniques[siren]) and not masque(l):
                        uniques[siren] = {**l, "_dep": dep}
                else:
                    uniques[siren] = {**l, "_dep": dep}
        par_dep[dep] = n
        total += n

    lignes = list(uniques.values())
    nb = len(lignes)

    # ---------- 1. comptage ----------
    print("1. COMPTAGE")
    codes = sorted(par_dep)
    for i in range(0, len(codes), 4):
        print("  ".join(f"{d:>3}:{par_dep[d]:>5}" for d in codes[i:i + 4]))
    manquants = [d for d in DEPARTEMENTS if d not in par_dep]
    print(f"Départements : {len(par_dep)} / {len(DEPARTEMENTS)}"
          + (f" (manquants : {', '.join(manquants)})" if manquants else ""))
    print(f"Lignes lues : {total}   Sociétés uniques (SIREN) : {nb}")

    # ---------- 2. structure ----------
    print("\n2. STRUCTURE D'UNE AGENCE")
    for c in champs:
        v = (exemple.get(c) or "").strip() or "(vide)"
        print(f"  {c:<17}: {v}")
    print(f"  (exemple : fichier {exemple_dep}, la plus complète vue)")
    print("Champs vides :")
    for c in champs:
        if c not in ("source", "date_collecte"):
            print(f"  {c:<17}{vides[c]:>7}  ({pct(vides[c], total)})")
    problemes = []
    if colonnes_ko:
        problemes.append("colonnes inattendues dans : " + ", ".join(colonnes_ko[:10]))
    if mauvais_siren:
        problemes.append(f"{mauvais_siren} SIREN invalides")
    if mauvais_siret:
        problemes.append(f"{mauvais_siret} SIRET invalides")
    if cp_ko:
        problemes.append(f"{cp_ko} codes postaux hors département, ex. " + ", ".join(exemples_cp))
    masques = sum(1 for l in lignes if masque(l))
    print("Problèmes : " + ("; ".join(problemes) if problemes else "aucun"))
    print(f"Info : {masques} sociétés ont une adresse masquée [NON-DIFFUSIBLE] (pas une erreur)")

    # ---------- 3. doublons ----------
    print("\n3. DOUBLONS")
    print(f"Par SIREN : {len(doublons_siren)} lignes en trop"
          + (", ex. " + ", ".join(f"{s} ({a}/{b})" for s, a, b in doublons_siren[:3])
             if doublons_siren else ""))
    print(f"Par SIRET (siège) : {doublons_siret} lignes en trop")
    gerant_soc = defaultdict(set)
    for l in lignes:
        for _, cle in valides(l.get("gerants")):
            gerant_soc[cle].add(l["siren"])
    print(f"Gérants distincts : {len(gerant_soc)}")
    for s in (2, 5, 10, 20):
        g = [len(v) for v in gerant_soc.values() if len(v) >= s]
        print(f"  dans {s} sociétés ou plus : {len(g)} gérants ({sum(g)} sociétés)")
    adr = defaultdict(set)
    for l in lignes:
        if not masque(l) and (l.get("adresse") or "").strip():
            adr[normaliser(l["adresse"])].add(l["siren"])
    partagees = [len(v) for v in adr.values() if len(v) >= 2]
    print(f"Même adresse pour 2 sociétés ou plus : {len(partagees)} adresses ({sum(partagees)} sociétés)")
    sans_gerant = sum(1 for l in lignes if not list(valides(l.get("gerants"))))
    print(f"Sans gérant exploitable : {sans_gerant} ({pct(sans_gerant, nb)})")

    # ---------- 4. réseaux ----------
    print("\n4. RÉSEAUX (enseigne et nom)")
    avec_ens = [l for l in lignes if (l.get("enseigne") or "").strip()]
    ens_distinctes = {normaliser(e) for l in avec_ens for e in l["enseigne"].split(" | ") if e.strip()}
    print(f"Sociétés avec une enseigne : {len(avec_ens)} ({pct(len(avec_ens), nb)}), "
          f"{len(ens_distinctes)} enseignes distinctes")

    candidats = []                     # (source, motif, nb, exemples)

    def groupes(source, valeur_de):
        g = defaultdict(list)
        for l in lignes:
            vals = {marque(v) for v in valeur_de(l)}
            for m in vals:
                if m:
                    g[m].append(l)
        gros = sorted(((m, ls) for m, ls in g.items() if len(ls) >= 5),
                      key=lambda x: -len(x[1]))
        for m, ls in gros:
            ex = " / ".join((x.get("enseigne") or x.get("nom") or "")[:30] for x in ls[:2])
            candidats.append((source, m, len(ls), ex))
        return gros

    g_ens = groupes("enseigne", lambda l: [e for e in (l.get("enseigne") or "").split(" | ") if e.strip()])
    print(f"Motifs d'ENSEIGNE sur 5 sociétés ou plus : {len(g_ens)} ({sum(len(x) for _, x in g_ens)} sociétés)")
    for m, ls in g_ens[:10]:
        print(f"  {m} : {len(ls)}")
    g_nom = groupes("nom", lambda l: [l.get("nom") or ""])
    print(f"Motifs de NOM sur 5 sociétés ou plus : {len(g_nom)} (bruyant : noms de famille, mots courants)")
    for m, ls in g_nom[:10]:
        print(f"  {m} : {len(ls)}")

    connus = []
    if os.path.exists("reseaux.txt"):
        with open("reseaux.txt", encoding="utf-8") as f:
            connus = [(n.strip(), normaliser(n)) for n in f if normaliser(n)]
    soc_reseau = set()
    trouves_connus = Counter()
    for l in lignes:
        en = " " + normaliser(l.get("enseigne")) + " "
        ec = en.replace(" ", "")
        nm = " " + normaliser(l.get("nom")) + " "
        for nom_r, cle in connus:
            if f" {cle} " in en or ec == cle.replace(" ", "") or f" {cle} " in nm:
                trouves_connus[nom_r] += 1
                soc_reseau.add(l["siren"])
    if connus:
        print(f"Réseaux de reseaux.txt trouvés : {len(trouves_connus)} sur {len(connus)} "
              f"({len(soc_reseau)} sociétés)")
    else:
        print("reseaux.txt absent : réseaux connus non cherchés")

    with open("reseaux_candidats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "motif", "nb_societes", "exemples"])
        w.writerows(sorted(candidats, key=lambda x: (x[0], -x[2])))

    # ---------- 5. indépendants ----------
    print("\n5. INDÉPENDANTS")
    def a_reseau(l):
        if (l.get("enseigne") or "").strip():
            return True
        return l["siren"] in soc_reseau
    indep = [l for l in lignes if not a_reseau(l)]
    print(f"Sans enseigne et sans réseau connu dans le nom : {len(indep)} ({pct(len(indep), nb)})")
    if "nature_juridique" in (champs or []):
        nj = Counter((l.get("nature_juridique") or "").strip() for l in lignes)
        ei = nj.get("1000", 0)
        print(f"Code 1000 (entrepreneur individuel) : {ei} ({pct(ei, nb)})")
        for code, n in nj.most_common(6):
            print(f"  {code or '(vide)'} {JURIDIQUES.get(code, '')} : {n}")
        print("  Attention : 1000 = personne physique, pas forcément « hors réseau »")
        print("  (beaucoup de mandataires de réseaux, IAD, Safti, Capifrance, sont en 1000).")
    else:
        print("Colonne nature_juridique absente : relancer fetch_sirene.py (force) pour l'avoir.")

    # ---------- dédoublonnage / filtre ----------
    sortie = list(lignes)
    if filtrer:
        garde = []
        retire_sg = retire_gros = 0
        for l in sortie:
            parts = list(valides(l.get("gerants")))
            if not parts:
                retire_sg += 1
                continue
            ok = [t for t, cle in parts if len(gerant_soc[cle]) < seuil]
            if not ok:
                retire_gros += 1
                continue
            l["gerants"] = " | ".join(ok)
            garde.append(l)
        sortie = garde
        print(f"\nFiltre : {retire_sg} retirées (sans gérant), "
              f"{retire_gros} retirées (gérants dans {seuil} sociétés ou plus)")
    with open("agences_uniques.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        w.writerows(sortie)
    print(f"\n{len(sortie)} sociétés écrites dans agences_uniques.csv")
    print("Motifs à relire : reseaux_candidats.csv")


if __name__ == "__main__":
    main()
        
