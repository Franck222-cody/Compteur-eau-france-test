#!/usr/bin/env python3

import csv
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"
METHOD_VERSION = "V1.3-test"

OUTPUT_DIR = Path("data_v1")
LATEST_FILE = OUTPUT_DIR / "latest_v1.json"
HISTORY_FILE = OUTPUT_DIR / "historique_v1.csv"

MAX_LOOKBACK_DAYS = 10
PAUSE = 0.05

STATION_LIST = [
    ("Seine", "H320000104", "Seine a Vernon", True),
    ("Loire", "M530001010", "Loire a Montjean-sur-Loire", True),
    ("Rhone", "V720001002", "Rhone a Tarascon", True),
    ("Garonne", "O900001002", "Garonne a Tonneins", True),
    ("Dordogne", "P555001001", "Dordogne a Pessac-sur-Dordogne", True),

    ("Adour_principal", "Q312001002", "Adour principal", False),
    ("Gave_de_Pau", "Q523101001", "Gave de Pau", False),
    ("Gave_Oloron", "Q741291001", "Gave d'Oloron", False),
    ("Nive", "Q931251001", "Nive", False),

    ("Charente", "R520001001", "Charente a Saintes", False),
    ("Vilaine", "J790061002", "Vilaine a Langon", False),
    ("Somme", "E647091003", "Somme", False),
    ("Orne", "I353101001", "Orne a Grimbosq", False),
    ("Vire", "I522101001", "Vire", False),
    ("Sienne", "I711101001", "Sienne", False),
    ("Selune", "I922102001", "Selune", False),

    ("Aude", "Y142201002", "Aude", False),
    ("Herault", "Y237002001", "Herault", False),
    ("Orb", "Y258002002", "Orb", False),

    ("Aulne", "J381181001", "Aulne a Chateauneuf-du-Faou", False),
    ("Blavet", "J571211005", "Blavet a Languidic", False),
    ("Odet", "J421191001", "Odet", False),
    ("Elorn", "J340301001", "Elorn", False),
    ("Trieux", "J171171001", "Trieux", False),
    ("Leguer", "J223302001", "Leguer", False),
    ("Scorff", "J510221001", "Scorff", False),
    ("Rance", "J061161001", "Rance", False),
]

STATIONS = {
    name: {
        "code": code,
        "nom": label,
        "obligatoire": required,
    }
    for name, code, label, required in STATION_LIST
}

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

ADOUR_COMPONENTS = [
    "Adour_principal",
    "Gave_de_Pau",
    "Gave_Oloron",
    "Nive",
]

EXPECTED_EXUTOIRES = DIRECT_EXUTOIRES + [
    "Gironde",
    "Adour",
]


def fetch_qmj(code, day):

    params = {
        "code_entite": code,
        "date_debut_obs_elab": day.isoformat(),
        "date_fin_obs_elab": day.isoformat(),
        "grandeur_hydro_elab": "QmnJ",
        "size": 20,
    }

    request = Request(
        BASE_URL + "?" + urlencode(params),
        headers={
            "User-Agent":
            "Compteur-Eau-Douce-France-V1/1.3"
        },
    )

    try:

        with urlopen(
            request,
            timeout=30,
        ) as response:

            payload = json.load(response)

    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:

        print(
            f"Erreur API {code}: {exc}"
        )

        return None

    for row in payload.get(
        "data",
        [],
    ):

        value = row.get(
            "resultat_obs_elab"
        )

        if value is None:
            continue

        try:

            debit = (
                float(value) / 1000.0
            )

        except (
            TypeError,
            ValueError,
        ):

            continue

        return {
            "debit_m3_s": debit,
            "date": day.isoformat(),
            "statut":
                row.get(
                    "statut_obs_elab"
                ),
            "qualification":
                row.get(
                    "qualification_obs_elab"
                ),
        }

    return None


def required_names():

    return [
        name
        for name, info
        in STATIONS.items()
        if info["obligatoire"]
    ]


def collect_day(
    day,
    initial=None,
):

    results = dict(
        initial or {}
    )

    for name, info in STATIONS.items():

        if name in results:
            continue

        obs = fetch_qmj(
            info["code"],
            day,
        )

        time.sleep(PAUSE)

        if obs is None:

            print(
                f"  MANQUANT: {name}"
            )

        else:

            results[name] = obs

            print(
                f"  OK {name}: "
                f"{obs['debit_m3_s']:.3f} m3/s"
            )

    return results


def latest_common_day():

    yesterday = (
        date.today()
        - timedelta(days=1)
    )

    for offset in range(
        MAX_LOOKBACK_DAYS + 1
    ):

        day = (
            yesterday
            - timedelta(days=offset)
        )

        core = {}
        ok = True

        print(
            f"Test date: {day}"
        )

        for name in required_names():

            info = STATIONS[name]

            obs = fetch_qmj(
                info["code"],
                day,
            )

            time.sleep(PAUSE)

            if obs is None:

                print(
                    f"  MANQUANT: {name}"
                )

                ok = False
                break

            core[name] = obs

            print(
                f"  OK {name}: "
                f"{obs['debit_m3_s']:.3f} m3/s"
            )

        if ok:

            return day, core

    raise RuntimeError(
        "Aucune date commune trouvee "
        "pour les 5 stations principales."
    )


def core_complete(results):

    return all(
        name in results
        for name in required_names()
    )


def build_exutoires(results):

    exutoires = {}

    for name in DIRECT_EXUTOIRES:

        obs = results.get(name)

        if obs is None:
            continue

        q = obs["debit_m3_s"]

        exutoires[name] = {
            "type":
                "mesure_ou_reference",
            "debit_m3_s":
                round(q, 3),
            "volume_m3_jour":
                round(q * 86400),
            "stations":
                [name],
        }

    if (
        "Garonne" in results
        and "Dordogne" in results
    ):

        q = (
            results[
                "Garonne"
            ]["debit_m3_s"]
            +
            results[
                "Dordogne"
            ]["debit_m3_s"]
        )

        exutoires["Gironde"] = {
            "type":
                "reconstitue",
            "debit_m3_s":
                round(q, 3),
            "volume_m3_jour":
                round(q * 86400),
            "stations": [
                "Garonne",
                "Dordogne",
            ],
            "note":
                "Garonne + Dordogne, "
                "sans double comptage.",
        }

    if all(
        name in results
        for name in ADOUR_COMPONENTS
    ):

        q = sum(
            results[
                name
            ]["debit_m3_s"]
            for name
            in ADOUR_COMPONENTS
        )

        exutoires["Adour"] = {
            "type":
                "reconstitue",
            "debit_m3_s":
                round(q, 3),
            "volume_m3_jour":
                round(q * 86400),
            "stations":
                ADOUR_COMPONENTS,
            "note":
                "Adour principal + "
                "Gave de Pau + "
                "Gave d'Oloron + Nive.",
        }

    return exutoires


def daily_summary(
    day,
    results,
):

    exutoires = build_exutoires(
        results
    )

    missing_stations = [
        name
        for name in STATIONS
        if name not in results
    ]

    missing_exutoires = [
        name
        for name in EXPECTED_EXUTOIRES
        if name not in exutoires
    ]

    q = sum(
        item["debit_m3_s"]
        for item
        in exutoires.values()
    )

    volume = sum(
        item["volume_m3_jour"]
        for item
        in exutoires.values()
    )

    station_count = len(results)
    station_expected = len(STATIONS)

    exutoire_count = len(
        exutoires
    )

    exutoire_expected = len(
        EXPECTED_EXUTOIRES
    )

    return {
        "date":
            day.isoformat(),

        "debit_m3_s":
            round(q, 3),

        "volume_m3_jour":
            round(volume),

        "stations_disponibles":
            station_count,

        "stations_prevues":
            station_expected,

        "couverture_stations_pct":
            round(
                100
                * station_count
                / station_expected,
                1,
            ),

        "stations_manquantes":
            ";".join(
                missing_stations
            ),

        "exutoires_disponibles":
            exutoire_count,

        "exutoires_prevus":
            exutoire_expected,

        "couverture_exutoires_pct":
            round(
                100
                * exutoire_count
                / exutoire_expected,
                1,
            ),

        "exutoires_manquants":
            ";".join(
                missing_exutoires
            ),

        "method_version":
            METHOD_VERSION,
    }


def hydro_start(day):

    if day.month >= 9:
        year = day.year
    else:
        year = day.year - 1

    return date(
        year,
        9,
        1,
    )


def load_history():

    rows = {}

    if not HISTORY_FILE.exists():
        return rows

    with HISTORY_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        for row in csv.DictReader(
            file
        ):

            if row.get("date"):

                rows[
                    row["date"]
                ] = row

    return rows


def history_needs_rebuild(
   
