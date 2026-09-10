#!/usr/bin/env python3

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# COMPTEUR EAU DOUCE FRANCE - COLLECTEUR V1
# Version de test : n'écrase PAS le compteur public actuel.
# Les résultats sont enregistrés dans le dossier data_v1/
# ============================================================

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"

METHOD_VERSION = "V1.1-test"

OUTPUT_DIR = Path("data_v1")
LATEST_FILE = OUTPUT_DIR / "latest_v1.json"
HISTORY_FILE = OUTPUT_DIR / "historique_v1.csv"

MAX_LOOKBACK_DAYS = 10


# ------------------------------------------------------------
# STATIONS
# ------------------------------------------------------------

STATIONS = {
    # 5 stations principales déjà utilisées
    "Seine": {
        "code": "H320000104",
        "nom": "Seine à Vernon",
        "obligatoire": True,
    },
    "Loire": {
        "code": "M530001010",
        "nom": "Loire à Montjean-sur-Loire",
        "obligatoire": True,
    },
    "Rhone": {
        "code": "V720001002",
        "nom": "Rhône à Tarascon",
        "obligatoire": True,
    },
    "Garonne": {
        "code": "O900001002",
        "nom": "Garonne à Tonneins",
        "obligatoire": True,
    },
    "Dordogne": {
        "code": "P555001001",
        "nom": "Dordogne à Pessac-sur-Dordogne",
        "obligatoire": True,
    },

    # Adour reconstitué
    "Adour_principal": {
        "code": "Q312001002",
        "nom": "Adour principal",
        "obligatoire": False,
    },
    "Gave_de_Pau": {
        "code": "Q523101001",
        "nom": "Gave de Pau",
        "obligatoire": False,
    },
    "Gave_Oloron": {
        "code": "Q741291001",
        "nom": "Gave d'Oloron",
        "obligatoire": False,
    },
    "Nive": {
        "code": "Q931251001",
        "nom": "Nive",
        "obligatoire": False,
    },

    # Façade Atlantique / Manche
    "Charente": {
        "code": "R520001001",
        "nom": "Charente à Saintes",
        "obligatoire": False,
    },
    "Vilaine": {
        "code": "J790061002",
        "nom": "Vilaine à Langon",
        "obligatoire": False,
    },
    "Somme": {
        "code": "E647091003",
        "nom": "Somme",
        "obligatoire": False,
    },
    "Orne": {
        "code": "I353101001",
        "nom": "Orne à Grimbosq",
        "obligatoire": False,
    },
    "Vire": {
        "code": "I522101001",
        "nom": "Vire",
        "obligatoire": False,
    },
    "Sienne": {
        "code": "I711101001",
        "nom": "Sienne",
        "obligatoire": False,
    },
    "Selune": {
        "code": "I922102001",
        "nom": "Sélune",
        "obligatoire": False,
    },

    # Méditerranée
    "Aude": {
        "code": "Y142201002",
        "nom": "Aude",
        "obligatoire": False,
    },
    "Herault": {
        "code": "Y237002001",
        "nom": "Hérault",
        "obligatoire": False,
    },
    "Orb": {
        "code": "Y258002002",
        "nom": "Orb",
        "obligatoire": False,
    },

    # Bretagne
    "Aulne": {
        "code": "J381181001",
        "nom": "Aulne à Châteauneuf-du-Faou",
        "obligatoire": False,
    },
    "Blavet": {
        "code": "J571211005",
        "nom": "Blavet à Languidic",
        "obligatoire": False,
    },
    "Odet": {
        "code": "J421191001",
        "nom": "Odet",
        "obligatoire": False,
    },
    "Elorn": {
        "code": "J340301001",
        "nom": "Élorn",
        "obligatoire": False,
    },
    "Trieux": {
        "code": "J171171001",
        "nom": "Trieux",
        "obligatoire": False,
    },
    "Leguer": {
        "code": "J223302001",
        "nom": "Léguer",
        "obligatoire": False,
    },
    "Scorff": {
        "code": "J510221001",
        "nom": "Scorff",
        "obligatoire": False,
    },
    "Rance": {
        "code": "J061161001",
        "nom": "Rance",
        "obligatoire": False,
    },
}


# Stations directement comptées comme exutoires indépendants.
# Garonne + Dordogne sont regroupées dans "Gironde".
# Les 4 stations Adour sont regroupées dans "Adour".
DIRECT_EXUTOIRES = [
    "Seine",
    "Loire",
    "Rhone",
    "Charente",
    "Vilaine",
    "Somme",
    "Orne",
    "Vire",
    "Sienne",
    "Selune",
    "Aude",
    "Herault",
    "Orb",
    "Aulne",
    "Blavet",
    "Odet",
    "Elorn",
    "Trieux",
    "Leguer",
    "Scorff",
    "Rance",
]


def fetch_qmj(code, day):
    """
    Récupère le débit moyen journalier QmnJ pour une station.
    Hub'Eau renvoie le résultat en litres/seconde.
    Conversion en m3/s : division par 1000.
    """

    params = {
        "code_entite": code,
        "date_debut_obs_elab": day.isoformat(),
        "date_fin_obs_elab": day.isoformat(),
        "grandeur_hydro_elab": "QmnJ",
        "size": 20,
    }

    url = BASE_URL + "?" + urlencode(params)

    req = Request(
        url,
        headers={
            "User-Agent": "Compteur-Eau-Douce-France-V1/1.1"
        },
    )

    try:
        with urlopen(req, timeout=30) as response:
            payload = json.load(response)

    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Erreur API {code} : {exc}")
        return None

    rows = payload.get("data", [])

    if not rows:
        return None

    for row in rows:
        resultat = row.get("resultat_obs_elab")

        if resultat is None:
            continue

        try:
            debit_m3_s = float(resultat) / 1000.0
        except (TypeError, ValueError):
            continue

        return {
            "debit_m3_s": debit_m3_s,
            "date": day.isoformat(),
            "statut": row.get("statut_obs_elab"),
            "qualification": row.get("qualification_obs_elab"),
        }

    return None


def find_latest_common_day():
    """
    Recherche la journée la plus récente pour laquelle les
    5 stations principales disposent toutes d'une donnée.
    """

    mandatory = {
        name: info
        for name, info in STATIONS.items()
        if info["obligatoire"]
    }

    yesterday = date.today() - timedelta(days=1)

    for offset in range(MAX_LOOKBACK_DAYS + 1):
        candidate = yesterday - timedelta(days=offset)

        print(f"Test de la date : {candidate}")

        results = {}
        complete = True

        for name, info in mandatory.items():
            obs = fetch_qmj(info["code"], candidate)

            if obs is None:
                print(f"  MANQUANT : {name}")
                complete = False
                break

            results[name] = obs
            print(
                f"  OK {name} : "
                f"{obs['debit_m3_s']:.2f} m3/s"
            )

        if complete:
            return candidate, results

    raise RuntimeError(
        "Aucune date commune trouvée pour les 5 stations "
        f"principales sur les {MAX_LOOKBACK_DAYS + 1} derniers jours."
    )


def collect_all_stations(target_day, initial_results):
    """
    Récupère toutes les stations V1 pour la même journée.
    Une station secondaire absente n'empêche pas la publication.
    """

    results = dict(initial_results)

    for name, info in STATIONS.items():

        if name in results:
            continue

        obs = fetch_qmj(info["code"], target_day)

        if obs is None:
            print(f"OPTIONNEL MANQUANT : {name}")
            continue

        results[name] = obs

        print(
            f"OK {name} : "
            f"{obs['debit_m3_s']:.2f} m3/s"
        )

    return results


def make_station_details(results):
    details = {}

    for name, info in STATIONS.items():

        obs = results.get(name)

        details[name] = {
            "code": info["code"],
            "nom": info["nom"],
            "disponible": obs is not None,
        }

        if obs:
            details[name].update(obs)

    return details


def build_exutoires(results):
    """
    Construit les exutoires sans double comptage.
    """

    exutoires = {}

    # --------------------------------------------------------
    # Exutoires directs
    # --------------------------------------------------------
    for name in DIRECT_EXUTOIRES:

        obs = results.get(name)

        if obs is None:
            continue

        exutoires[name] = {
            "type": "mesure_ou_reference",
            "debit_m3_s": obs["debit_m3_s"],
            "volume_m3_jour": obs["debit_m3_s"] * 86400,
            "stations": [name],
        }

    # --------------------------------------------------------
    # GIRONDE = Garonne + Dordogne
    # --------------------------------------------------------
    if (
        results.get("Garonne") is not None
        and results.get("Dordogne") is not None
    ):
        debit = (
            results["Garonne"]["debit_m3_s"]
            + results["Dordogne"]["debit_m3_s"]
        )

        exutoires["Gironde"] = {
            "type": "reconstitue",
            "debit_m3_s": debit,
            "volume_m3_jour": debit * 86400,
            "stations": [
                "Garonne",
                "Dordogne",
            ],
            "note": (
                "Reconstitution à partir de la Garonne "
                "et de la Dordogne."
            ),
        }

    # --------------------------------------------------------
    # ADOUR = Adour principal + Gave de Pau
    #         + Gave d'Oloron + Nive
    # --------------------------------------------------------
    adour_components = [
        "Adour_principal",
        "Gave_de_Pau",
        "Gave_Oloron",
        "Nive",
    ]

    if all(results.get(name) is not None for name in adour_components):

        debit = sum(
            results[name]["debit_m3_s"]
            for name in adour_components
        )

        exutoires["Adour"] = {
            "type": "reconstitue",
            "debit_m3_s": debit,
            "volume_m3_jour": debit * 86400,
            "stations": adour_components,
            "note": (
                "Reconstitution V1 à partir de quatre "
                "composantes hydrologiques."
            ),
        }

    return exutoires


def build_payload(target_day, results, exutoires):

    total_debit = sum(
        item["debit_m3_s"]
        for item in exutoires.values()
    )

    total_volume = total_debit * 86400

    stations_available = len(results)
    stations_expected = len(STATIONS)

    station_coverage = (
        stations_available / stations_expected * 100
        if stations_expected
        else 0
    )

    expected_exutoires = len(DIRECT_EXUTOIRES) + 2
    available_exutoires = len(exutoires)

    exutoire_coverage = (
        available_exutoires / expected_exutoires * 100
        if expected_exutoires
        else 0
    )

    return {
        "date": target_day.isoformat(),

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "method_version": METHOD_VERSION,

        "source": {
            "nom": "Hub'Eau Hydrometrie",
            "grandeur": "QmnJ",
            "unite_source": "l/s",
            "unite_utilisee": "m3/s",
        },

        "total": {
            "type": "mesure_reconstituee",
            "debit_m3_s": round(total_debit, 3),
            "volume_m3_jour": round(total_volume),
            "stations_disponibles": stations_available,
            "stations_prevues": stations_expected,
            "couverture_stations_pct": round(
                station_coverage, 1
            ),
            "exutoires_disponibles": available_exutoires,
            "exutoires_prevus": expected_exutoires,
            "couverture_exutoires_pct": round(
                exutoire_coverage, 1
            ),
        },

        "exutoires": exutoires,

        "stations": make_station_details(results),

        "avertissement": (
            "Version V1 de test. Le total représente uniquement "
            "les flux mesurés ou reconstitués par le réseau V1. "
            "Il ne comprend pas encore l'estimation des zones "
            "non jaugées et ne constitue donc pas encore le "
            "total national France."
        ),
    }


def save_latest(payload):

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with LATEST_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Créé : {LATEST_FILE}")


def update_history(payload):

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "date",
        "debit_m3_s",
        "volume_m3_jour",
        "stations_disponibles",
        "stations_prevues",
        "couverture_stations_pct",
        "exutoires_disponibles",
        "exutoires_prevus",
        "couverture_exutoires_pct",
        "method_version",
    ]

    new_row = {
        "date": payload["date"],
        "debit_m3_s": payload["total"]["debit_m3_s"],
        "volume_m3_jour": payload["total"]["volume_m3_jour"],
        "stations_disponibles":
            payload["total"]["stations_disponibles"],
        "stations_prevues":
            payload["total"]["stations_prevues"],
        "couverture_stations_pct":
            payload["total"]["couverture_stations_pct"],
        "exutoires_disponibles":
            payload["total"]["exutoires_disponibles"],
        "exutoires_prevus":
            payload["total"]["exutoires_prevus"],
        "couverture_exutoires_pct":
            payload["total"]["couverture_exutoires_pct"],
        "method_version": METHOD_VERSION,
    }

    rows = []

    if HISTORY_FILE.exists():

        with HISTORY_FILE.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                if row.get("date") != payload["date"]:
                    rows.append(row)

    rows.append(new_row)

    rows.sort(
        key=lambda row: row["date"]
    )

    with HISTORY_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Mis à jour : {HISTORY_FILE}")


def main():

    print("")
    print("========================================")
    print(" COMPTEUR EAU DOUCE FRANCE - V1 TEST")
    print("========================================")
    print("")

    target_day, core_results = find_latest_common_day()

    print("")
    print(f"Date retenue : {target_day}")
    print("")

    results = collect_all_stations(
        target_day,
        core_results,
    )

    exutoires = build_exutoires(results)

    payload = build_payload(
        target_day,
        results,
        exutoires,
    )

    save_latest(payload)
    update_history(payload)

    print("")
    print("----------------------------------------")
    print(
        "Débit mesuré/reconstitué : "
        f"{payload['total']['debit_m3_s']:.2f} m3/s"
    )
    print(
        "Volume journalier : "
        f"{payload['total']['volume_m3_jour']:,} m3"
    )
    print(
        "Stations : "
        f"{payload['total']['stations_disponibles']}"
        f"/{payload['total']['stations_prevues']}"
    )
    print(
        "Exutoires : "
        f"{payload['total']['exutoires_disponibles']}"
        f"/{payload['total']['exutoires_prevus']}"
    )
    print("----------------------------------------")
    print("")
    print(
        "TEST UNIQUEMENT : aucune donnée du compteur "
        "public actuel n'a été remplacée."
    )


if __name__ == "__main__":
    main()
