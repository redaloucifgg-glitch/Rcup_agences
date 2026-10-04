"""Ajoute l'effectif de chaque agence (API Recherche d'entreprises, gratuite, sans clé).

Colonnes ajoutées :
  effectif_code    code INSEE de la tranche (ex. 11)
  effectif         libellé (ex. 10 à 19 salariés)
  effectif_annee   année de la donnée
  effectif_siege   libellé pour l'établissement siège (vérifié avec siret_siege)
  effectif_statut  ok / introuvable / HTTPxxx / erreur

Usage :
  python recuperer_effectifs.py                      tout agences_independantes.csv
  python recuperer_effectifs.py --echantillon 50     seulement 50 lignes (pour essayer)
  python recuperer_effectifs.py --workers 4 --pause 0.8
  python recuperer_effectifs.py --duree-max 330      s'arrête proprement après 330 min
  python recuperer_effectifs.py mon_fichier.csv      autre fichier

Les lignes déjà en ok ou introuvable ne sont pas re-testées : on peut relancer pour reprendre.
"""
import csv
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

API = "https://recherche-entreprises.api.gouv.fr/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (enrichissement effectifs)"}
COLONNES = ["effectif_code", "effectif", "effectif_annee", "effectif_siege", "effectif_statut"]
DEFINITIFS = {"ok", "introuvable"}
TRANCHES = {
    "NN": "Non employeuse",
    "00": "0 salarié",
    "01": "1 à 2 salariés",
    "02": "3 à 5 salariés",
    "03": "6 à 9 salariés",
    "11": "10 à 19 salariés",
    "12": "20 à 49 salariés",
    "21": "50 à 99 salariés",
    "22": "100 à 199 salariés",
    "31": "200 à 249 salariés",
    "32": "250 à 499 salariés",
    "41": "500 à 999 salariés",
    "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés",
    "52": "5 000 à 9 999 salariés",
    "53": "10 000 salariés et plus",
}


def interroger(l, pause):
    siren = (l.get("siren") or "").strip()
    siret = (l.get("siret_siege") or "").strip()
    for essai in range(4):
        try:
            r = requests.get(API, params={"q": siren, "per_page": 1},
                             headers=HEADERS, timeout=20)
        except requests.RequestException:
            time.sleep(2 * (essai + 1))
            continue
        if r.status_code == 429:                  # trop de requêtes : on attend
            try:
                attente = int(r.headers.get("Retry-After", 5))
            except ValueError:
                attente = 5
            time.sleep(max(attente, 5) * (essai + 1))
            continue
        time.sleep(pause)
        if r.status_code != 200:
            return {"effectif_statut": f"HTTP{r.status_code}"}
        try:
            resultats = r.json().get("results") or []
        except ValueError:
            return {"effectif_statut": "erreur"}
        res = next((x for x in resultats if x.get("siren") == siren), None)
        if not res:
            return {"effectif_statut": "introuvable"}
        code = res.get("tranche_effectif_salarie") or ""
        siege = res.get("siege") or {}
        code_siege = ""
        if siret and siege.get("siret") == siret:
            code_siege = siege.get("tranche_effectif_salarie") or ""
        return {
            "effectif_code": code,
            "effectif": TRANCHES.get(code, ""),
            "effectif_annee": res.get("annee_tranche_effectif_salarie") or "",
            "effectif_siege": TRANCHES.get(code_siege, ""),
            "effectif_statut": "ok",
        }
    return {"effectif_statut": "erreur"}


def ecrire(fichier, champs, lignes):
    with open(fichier, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)


def main():
    args = sys.argv[1:]
    echantillon, workers, pause, duree_max = 0, 4, 0.8, 0.0
    for nom in ("--echantillon", "--workers", "--pause", "--duree-max"):
        if nom in args:
            i = args.index(nom)
            valeur = args[i + 1]
            del args[i:i + 2]
            if nom == "--echantillon":
                echantillon = int(valeur)
            elif nom == "--workers":
                workers = int(valeur)
            elif nom == "--pause":
                pause = float(valeur)
            else:
                duree_max = float(valeur)
    fichier = args[0] if args else "agences_independantes.csv"

    with open(fichier, newline="", encoding="utf-8") as f:
        lecteur = csv.DictReader(f)
        champs = list(lecteur.fieldnames)
        lignes = list(lecteur)
    if "siren" not in champs:
        sys.exit("Colonne siren absente.")
    for c in COLONNES:
        if c not in champs:
            champs.append(c)
            for l in lignes:
                l[c] = ""

    a_tester = [l for l in lignes
                if (l.get("siren") or "").strip()
                and (l.get("effectif_statut") or "") not in DEFINITIFS]
    if echantillon:
        a_tester = a_tester[:echantillon]
    print(f"{len(a_tester)} lignes à interroger (workers : {workers}, pause : {pause} s)")

    debut = time.time()
    fait = 0
    for i in range(0, len(a_tester), 500):
        lot = a_tester[i:i + 500]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for l, res in zip(lot, pool.map(lambda x: interroger(x, pause), lot)):
                for c in COLONNES:
                    l[c] = res.get(c, "")
        fait += len(lot)
        ecrire(fichier, champs, lignes)           # sauvegarde après chaque lot
        print(f"  {fait}/{len(a_tester)} traitées", flush=True)
        if duree_max and (time.time() - debut) / 60 >= duree_max:
            print(f"Durée maximale atteinte ({duree_max:.0f} min) : arrêt, relance pour continuer.")
            break

    ecrire(fichier, champs, lignes)
    statuts = Counter(l.get("effectif_statut") or "non traité" for l in lignes)
    print(f"\n{len(lignes)} lignes écrites dans {fichier}")
    for s, n in statuts.most_common():
        print(f"  {s:<14} {n}")
    tranches = Counter(l["effectif"] or "(vide)" for l in lignes if l.get("effectif_statut") == "ok")
    print("Répartition des effectifs :")
    for t, n in tranches.most_common():
        print(f"  {t:<26} {n}")


if __name__ == "__main__":
    main()
