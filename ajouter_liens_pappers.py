"""Ajoute lien_pappers (à partir du SIREN) et vérifie que chaque lien fonctionne.

Colonnes ajoutées : lien_pappers, lien_statut (code HTTP ou nom de l'erreur), lien_ok (oui/non)

Usage :
  python ajouter_liens_pappers.py                       tout le fichier agences_independantes.csv
  python ajouter_liens_pappers.py --echantillon 50      teste seulement 50 liens (pour essayer)
  python ajouter_liens_pappers.py --workers 3           moins de requêtes en parallèle
  python ajouter_liens_pappers.py mon_fichier.csv       autre fichier
"""
import csv
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (verification de liens)"}
DEFINITIFS = {"200", "404", "410"}


def verifier(siren):
    url = f"https://www.pappers.fr/entreprise/{siren}"
    statut = "ErreurReseau"
    for essai in range(3):
        try:
            r = requests.get(url, headers=HEADERS, allow_redirects=True,
                             timeout=15, stream=True)
            code = r.status_code
            r.close()
            if code == 429:                      # trop de requêtes : on attend et on réessaie
                statut = "429"
                time.sleep(5 * (essai + 1))
                continue
            return str(code)
        except requests.RequestException as e:
            statut = type(e).__name__
            time.sleep(2)
    return statut


def main():
    args = sys.argv[1:]
    echantillon, workers = 0, 5
    if "--echantillon" in args:
        i = args.index("--echantillon")
        echantillon = int(args[i + 1])
        del args[i:i + 2]
    if "--workers" in args:
        i = args.index("--workers")
        workers = int(args[i + 1])
        del args[i:i + 2]
    fichier = args[0] if args else "agences_independantes.csv"

    with open(fichier, newline="", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        champs = list(lecteur.fieldnames)
        lignes = list(lecteur)
    if "siren" not in champs:
        sys.exit("Colonne siren absente.")
    for c in ("lien_pappers", "lien_statut", "lien_ok"):
        if c not in champs:
            champs.append(c)

    for l in lignes:
        siren = (l.get("siren") or "").strip()
        l["lien_pappers"] = f"https://www.pappers.fr/entreprise/{siren}" if siren else ""

    a_tester = [l for l in lignes
                if l["lien_pappers"] and (l.get("lien_statut") or "") not in DEFINITIFS]
    if echantillon:
        a_tester = a_tester[:echantillon]
    print(f"{len(a_tester)} liens à vérifier (workers : {workers})")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for l, statut in zip(a_tester, pool.map(lambda x: verifier(x["siren"]), a_tester)):
            l["lien_statut"] = statut
            l["lien_ok"] = "oui" if statut == "200" else "non"

    with open(fichier, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(lignes)

    bilan = Counter(l.get("lien_statut") or "non testé" for l in lignes)
    print(f"{len(lignes)} lignes écrites dans {fichier}")
    for statut, n in bilan.most_common():
        print(f"  {statut:<15} {n}")


if __name__ == "__main__":
    main()
