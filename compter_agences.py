"""Compte les agences de data/agences_*.csv et vérifie la structure des fichiers.

Usage : python compter_agences.py              (dossier data/ par défaut)
        python compter_agences.py mon_dossier

Affiche : agences par département, total, départements manquants ou vides,
la structure d'une agence (colonnes + un exemple réel), puis les contrôles de structure (colonnes, doublons de SIREN, formats,
champs vides, cohérence code postal / département).
"""
import csv
import glob
import os
import re
import sys
from collections import Counter

DEPARTEMENTS = (
    [f"{i:02d}" for i in range(1, 96) if i != 20]
    + ["2A", "2B", "971", "972", "973", "974", "976"]
)
COLONNES = ["siren", "siret_siege", "nom", "enseigne", "adresse",
            "code_postal", "ville", "date_creation", "gerants",
            "source", "date_collecte"]


def cp_coherent(cp, dep):
    """Le code postal commence-t-il par le bon préfixe pour ce département ?"""
    if not cp:
        return True            # un cp vide est signalé à part, pas ici
    if dep in ("2A", "2B"):
        return cp.startswith("20")
    return cp.startswith(dep)


def main():
    dossier = sys.argv[1] if len(sys.argv) > 1 else "data"
    fichiers = sorted(glob.glob(os.path.join(dossier, "agences_*.csv")))
    if not fichiers:
        sys.exit(f"Aucun fichier agences_*.csv dans {dossier}/")

    par_dep = {}
    sirens = {}                       # siren -> premier département
    doublons = []                     # (siren, dep1, dep2)
    vides = Counter()                 # colonne -> nb de valeurs vides
    total = 0
    mauvais_siren = mauvais_siret = cp_incoherents = 0
    colonnes_ko = []
    exemples_cp = []
    exemple, exemple_dep, exemple_score = None, "", -1   # agence la plus complète vue

    for chemin in fichiers:
        dep = os.path.basename(chemin)[len("agences_"):-len(".csv")]
        n = 0
        with open(chemin, newline="", encoding="utf-8") as f:
            lecteur = csv.DictReader(f)
            if lecteur.fieldnames != COLONNES:
                colonnes_ko.append(dep)
            for l in lecteur:
                n += 1
                siren = (l.get("siren") or "").strip()
                siret = (l.get("siret_siege") or "").strip()
                if not re.fullmatch(r"\d{9}", siren):
                    mauvais_siren += 1
                if not (re.fullmatch(r"\d{14}", siret) and siret.startswith(siren)):
                    mauvais_siret += 1
                if siren in sirens:
                    doublons.append((siren, sirens[siren], dep))
                else:
                    sirens[siren] = dep
                for c in COLONNES:
                    if not (l.get(c) or "").strip():
                        vides[c] += 1
                score = sum(1 for c in COLONNES if (l.get(c) or "").strip())
                if score > exemple_score:
                    exemple, exemple_dep, exemple_score = dict(l), dep, score
                if not cp_coherent((l.get("code_postal") or "").strip(), dep):
                    cp_incoherents += 1
                    if len(exemples_cp) < 3:
                        exemples_cp.append(f"{siren} (fichier {dep}, cp {l.get('code_postal')})")
        par_dep[dep] = n
        total += n

    # --- comptage ---
    codes = sorted(par_dep)
    for i in range(0, len(codes), 4):
        print("  ".join(f"{d:>3}:{par_dep[d]:>5}" for d in codes[i:i + 4]))
    print("-" * 40)
    print(f"Départements : {len(par_dep)} / {len(DEPARTEMENTS)}")
    print(f"TOTAL AGENCES : {total}")
    print(f"SIREN uniques : {len(sirens)}")
    manquants = [d for d in DEPARTEMENTS if d not in par_dep]
    inconnus = [d for d in par_dep if d not in DEPARTEMENTS]
    vides_dep = [d for d, n in par_dep.items() if n == 0]
    if manquants:
        print("Manquants : " + ", ".join(manquants))
    if inconnus:
        print("Fichiers inattendus : " + ", ".join(inconnus))
    if vides_dep:
        print("Départements à 0 agence : " + ", ".join(vides_dep))

    # --- structure d'une agence ---
    print("-" * 40)
    print(f"STRUCTURE D'UNE AGENCE ({len(COLONNES)} colonnes)")
    print(f"Exemple réel (fichier {exemple_dep}, la plus complète vue) :")
    for c in COLONNES:
        valeur = (exemple.get(c) or "").strip() or "(vide)"
        print(f"  {c:<14}: {valeur}")

    # --- contrôle ---
    print("-" * 40)
    print("CONTRÔLE DE STRUCTURE")
    problemes = 0

    def ok(cond, message_ko):
        nonlocal problemes
        if cond:
            return
        problemes += 1
        print("  PROBLÈME : " + message_ko)

    ok(not colonnes_ko, "colonnes différentes de l'attendu dans : " + ", ".join(colonnes_ko[:10]))
    ok(not doublons, f"{len(doublons)} doublons de SIREN entre fichiers, ex. "
       + ", ".join(f"{s} ({a}/{b})" for s, a, b in doublons[:3]))
    ok(mauvais_siren == 0, f"{mauvais_siren} SIREN qui n'ont pas 9 chiffres")
    ok(mauvais_siret == 0, f"{mauvais_siret} SIRET invalides (14 chiffres commençant par le SIREN)")
    ok(cp_incoherents == 0, f"{cp_incoherents} code postal hors département, ex. " + ", ".join(exemples_cp))
    ok(not manquants, f"{len(manquants)} département(s) manquant(s)")
    if problemes == 0:
        print("  Aucun problème détecté.")

    print("Champs vides :")
    for c in COLONNES:
        if c in ("source", "date_collecte"):
            continue
        print(f"  {c:<14} {vides[c]:>7}  ({vides[c] / total:.0%})")


if __name__ == "__main__":
    main()
