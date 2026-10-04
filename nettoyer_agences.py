"""Garde surtout les agences indépendantes : retire dans l'ordre

  1. les entrepreneurs individuels (nature juridique 1000)
  2. les sociétés civiles (codes 65xx : SCI, etc.)
  3. les réseaux (reseaux.txt + motifs_reseaux.txt, cherchés dans l'ENSEIGNE)
  4. les sociétés sans gérant exploitable
  5. les gérants qui dirigent SEUIL sociétés ou plus (5 par défaut)

Usage :
  python nettoyer_agences.py                1re fois : écrit motifs_reseaux.txt (les 30 motifs
                                            d'enseigne les plus fréquents) et s'arrête
                                            -> relis-le, supprime les lignes qui ne sont pas des
                                               réseaux, puis relance la même commande
  python nettoyer_agences.py                2e fois : nettoie
  python nettoyer_agences.py --seuil 10     seuil gérant personnalisé
  python nettoyer_agences.py --avec-nom     retire aussi les noms contenant un réseau de
                                            reseaux.txt (plus bruyant : IAD, Era, Lamy...)
  python nettoyer_agences.py --sans-motifs  n'utilise que reseaux.txt, sans étape de validation

Entrée : agences_uniques.csv
Sorties : agences_independantes.csv (gardées), agences_retirees.csv (avec la raison)
"""
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

FORMES = {"sarl", "sas", "sasu", "eurl", "sa", "snc", "sci", "selarl", "sc", "ei",
          "eirl", "ste", "societe", "scp"}
GENERIQUES = {"agence", "agences", "cabinet", "groupe", "immobilier", "immobiliere",
              "immobiliers", "immo", "le", "la", "les", "l", "de", "du", "des", "d",
              "et", "en", "a", "au", "aux", "the", "mr", "mme", "m"}
NB_MOTIFS = 30


def normaliser(texte):
    texte = unicodedata.normalize("NFKD", texte or "")
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def tokens_sig(texte):
    if "non diffusible" in normaliser(texte):
        return []
    return [m for m in normaliser(texte).split()
            if m not in FORMES and m not in GENERIQUES and len(m) > 1]


def valides(gerants):
    for part in (gerants or "").split(" | "):
        m = re.search(r"\(([^)]*)\)\s*$", part)
        qualite = m.group(1).lower() if m else ""
        nom = re.sub(r"\s*\([^)]*\)\s*$", "", part).strip()
        if not nom or "non-diffusible" in nom.lower() or "commissaire" in qualite:
            continue
        yield part.strip(), normaliser(nom)


def charger(chemin):
    """Lignes d'un fichier de noms ; ce qui suit # est un commentaire."""
    liste = []
    if os.path.exists(chemin):
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                nom = ligne.split("#")[0].strip()
                if normaliser(nom):
                    liste.append((nom, normaliser(nom)))
    return liste


def enseignes_de(ligne):
    return [e.strip() for e in (ligne.get("enseigne") or "").split(" | ") if e.strip()]


def reseau_enseigne(ligne, liste):
    for e in enseignes_de(ligne):
        padded = " " + normaliser(e) + " "
        compact = padded.replace(" ", "")
        for nom, cle in liste:
            if f" {cle} " in padded or compact == cle.replace(" ", ""):
                return nom
    return None


def generer_motifs(lignes):
    groupes = defaultdict(list)           # premier mot -> liste d'enseignes
    for l in lignes:
        vus = set()
        for e in enseignes_de(l):
            t = tokens_sig(e)
            if t and t[0] not in vus:
                vus.add(t[0])
                groupes[t[0]].append(e)
    gros = sorted(((m, es) for m, es in groupes.items() if len(es) >= 5),
                  key=lambda x: -len(x[1]))[:NB_MOTIFS]
    with open("motifs_reseaux.txt", "w", encoding="utf-8") as f:
        f.write("# Motifs d'enseigne qui se répètent (réseaux possibles).\n")
        f.write("# Supprime (ou mets # devant) les lignes qui ne sont PAS un réseau,\n")
        f.write("# puis relance : python nettoyer_agences.py\n")
        f.write("# Tu peux aussi préciser un motif (ex. remplacer cote par cote france).\n\n")
        for m, es in gros:
            prefixes = Counter(" ".join(tokens_sig(e)[:2]) for e in es)
            pref, n = prefixes.most_common(1)[0]
            part = n / len(es)
            motif = pref if part >= 0.6 and " " in pref else m
            note = f"{len(es)} sociétés, ex. " + " / ".join(dict.fromkeys(es[:3]))
            if motif == m and len(prefixes) > 1 and part < 0.6:
                note += "  [AMBIGU : plusieurs enseignes différentes]"
            f.write(f"{motif}    # {note}\n")
    return len(gros)


def main():
    args = sys.argv[1:]
    seuil = 5
    if "--seuil" in args:
        i = args.index("--seuil")
        seuil = int(args[i + 1])
        del args[i:i + 2]
    avec_nom = "--avec-nom" in args
    sans_motifs = "--sans-motifs" in args
    args = [a for a in args if not a.startswith("--")]
    entree = args[0] if args else "agences_uniques.csv"

    with open(entree, newline="", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        champs = lecteur.fieldnames
        lignes = list(lecteur)
    if "nature_juridique" not in champs:
        sys.exit("Colonne nature_juridique absente : relance fetch_sirene.py (force) d'abord.")

    if not sans_motifs and not os.path.exists("motifs_reseaux.txt"):
        n = generer_motifs(lignes)
        print(f"{n} motifs écrits dans motifs_reseaux.txt.")
        print("Relis-le : supprime les lignes qui ne sont pas des réseaux, puis relance la commande.")
        return

    reseaux = charger("reseaux.txt") + ([] if sans_motifs else charger("motifs_reseaux.txt"))
    if not reseaux:
        print("ATTENTION : aucun réseau chargé (reseaux.txt introuvable ?).")
    reseaux_nom = charger("reseaux.txt")

    # nombre de sociétés par gérant (sur toute la liste, avant retraits)
    gerant_soc = defaultdict(set)
    for l in lignes:
        for _, cle in valides(l.get("gerants")):
            gerant_soc[cle].add(l["siren"])

    gardees, retirees = [], []
    etapes = Counter()
    reseaux_vus = Counter()
    nom_conserve = 0
    for l in lignes:
        nj = (l.get("nature_juridique") or "").strip()
        raison = ""
        if nj == "1000":
            raison = "1 entrepreneur individuel"
        elif nj.startswith("65"):
            raison = "2 société civile"
        else:
            r = reseau_enseigne(l, reseaux)
            if r:
                raison = "3 réseau"
                reseaux_vus[r] += 1
            else:
                nom_n = " " + normaliser(l.get("nom")) + " "
                rn = next((n for n, c in reseaux_nom if f" {c} " in nom_n), None)
                if rn and avec_nom:
                    raison = "3 réseau"
                    reseaux_vus[rn] += 1
                elif rn:
                    nom_conserve += 1
        if not raison:
            parts = list(valides(l.get("gerants")))
            if not parts:
                raison = "4 sans gérant exploitable"
            else:
                ok = [t for t, cle in parts if len(gerant_soc[cle]) < seuil]
                if not ok:
                    raison = f"5 gérants à {seuil} sociétés ou plus"
                else:
                    l["gerants"] = " | ".join(ok)
        if raison:
            etapes[raison] += 1
            retirees.append({**l, "raison": raison[2:]})
        else:
            gardees.append(l)

    with open("agences_independantes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(gardees)
    with open("agences_retirees.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs + ["raison"])
        w.writeheader()
        w.writerows(retirees)

    reste = len(lignes)
    print(f"Départ : {reste} sociétés")
    libelles = {"1": "entrepreneurs individuels", "2": "sociétés civiles",
                "3": "réseaux", "4": "sans gérant exploitable",
                "5": f"gérants à {seuil} sociétés ou plus"}
    for cle in sorted(etapes):
        reste -= etapes[cle]
        print(f"  - {etapes[cle]:>6} {libelles[cle[0]]:<32} -> reste {reste}")
    print(f"Gardées : {len(gardees)} -> agences_independantes.csv")
    print("Retirées (avec raison) -> agences_retirees.csv")
    if reseaux_vus:
        print("Réseaux les plus retirés : " + ", ".join(
            f"{n} ({c})" for n, c in reseaux_vus.most_common(10)))
    if nom_conserve and not avec_nom:
        print(f"{nom_conserve} sociétés gardées alors que leur NOM contient un réseau de "
              "reseaux.txt (relance avec --avec-nom pour les retirer)")


if __name__ == "__main__":
    main()
