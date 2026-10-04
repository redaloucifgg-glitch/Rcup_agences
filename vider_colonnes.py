"""Vide les colonnes de vérification des liens.

Usage :
  python vider_colonnes.py                  vide lien_statut et lien_ok
  python vider_colonnes.py --tout           vide aussi lien_pappers
  python vider_colonnes.py mon_fichier.csv  autre fichier
"""
import csv
import sys

args = sys.argv[1:]
tout = "--tout" in args
args = [a for a in args if not a.startswith("--")]
fichier = args[0] if args else "agences_independantes.csv"

a_vider = ["lien_statut", "lien_ok"] + (["lien_pappers"] if tout else [])

with open(fichier, newline="", encoding="utf-8") as f:
    lecteur = csv.DictReader(f)
    champs = list(lecteur.fieldnames)
    lignes = list(lecteur)

for l in lignes:
    for c in a_vider:
        if c in l:
            l[c] = ""

with open(fichier, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=champs)
    w.writeheader()
    w.writerows(lignes)

print(f"Colonnes vidées ({', '.join(a_vider)}) sur {len(lignes)} lignes")
