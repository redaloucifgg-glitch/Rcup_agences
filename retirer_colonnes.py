"""Supprime des colonnes d'un CSV.

Usage :
  python retirer_colonnes.py                          retire lien_statut et lien_ok
  python retirer_colonnes.py --colonnes a,b,c         retire les colonnes a, b et c
  python retirer_colonnes.py mon_fichier.csv          autre fichier
"""
import csv
import sys

args = sys.argv[1:]
colonnes = ["lien_statut", "lien_ok"]
if "--colonnes" in args:
    i = args.index("--colonnes")
    colonnes = [c.strip() for c in args[i + 1].split(",") if c.strip()]
    del args[i:i + 2]
fichier = args[0] if args else "agences_independantes.csv"

with open(fichier, newline="", encoding="utf-8") as f:
    lecteur = csv.DictReader(f)
    champs = list(lecteur.fieldnames)
    lignes = list(lecteur)

retirees = [c for c in colonnes if c in champs]
absentes = [c for c in colonnes if c not in champs]
champs = [c for c in champs if c not in colonnes]

with open(fichier, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
    w.writeheader()
    w.writerows(lignes)

print(f"Colonnes retirées : {', '.join(retirees) or 'aucune'}")
if absentes:
    print(f"Colonnes absentes (ignorées) : {', '.join(absentes)}")
print(f"{len(lignes)} lignes écrites dans {fichier}")
