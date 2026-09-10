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
METHOD_VERSION = "V1.2-test"

OUTPUT_DIR = Path("data_v1")
LATEST_FILE = OUTPUT_DIR / "latest_v1.json"
HISTORY_FILE = OUTPUT_DIR / "historique_v1.csv"

MAX_LOOKBACK_DAYS = 10
PAUSE = 0.05

# nom interne, code station, libelle, obligatoire
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
    name: {"code": code, "nom": label, "obligatoire": required}
    for name, code, label, required in STATION_LIST
}

DIRECT_EXUTOIRES = [
    "Seine", "Loire", "Rhone", "Charente", "Vilaine", "Somme",
    "Orne", "Vire", "Sienne", "Selune", "Aude", "Herault", "Orb",
    "Aulne", "Blavet", "Odet", "Elorn", "Trieux", "Leguer",
    "Scorff", "Rance",
]

ADOUR_COMPONENTS = [
    "Adour_principal", "Gave_de_Pau", "Gave_Oloron", "Nive"
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
        headers={"User-Agent": "Compteur-Eau-Douce-France-V1/1.2"},
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Erreur API {code}: {exc}")
        return None

    for row in payload.get("data", []):
        value = row.get("resultat_obs_elab")

        if value is None:
            continue

        try:
            debit = float(value) / 1000.0
        except (TypeError, ValueError):
            continue

        return {
            "debit_m3_s": debit,
            "date": day.isoformat(),
            "statut": row.get("statut_obs_elab"),
            "qualification": row.get("qualification_obs_elab"),
        }

    return None


def required_names():
    return [
        name for name, info in STATIONS.items()
        if info["obligatoire"]
    ]


def collect_day(day, initial=None):
    results = dict(initial or {})

    for name, info in STATIONS.items():
        if name in results:
            continue

        obs = fetch_qmj(info["code"], day)
        time.sleep(PAUSE)

        if obs is None:
            print(f"  MANQUANT: {name}")
        else:
            results[name] = obs
            print(f"  OK {name}: {obs['debit_m3_s']:.3f} m3/s")

    return results


def latest_common_day():
    yesterday = date.today() - timedelta(days=1)

    for offset in range(MAX_LOOKBACK_DAYS + 1):
        day = yesterday - timedelta(days=offset)
        core = {}
        ok = True

        print(f"Test date: {day}")

        for name in required_names():
            info = STATIONS[name]
            obs = fetch_qmj(info["code"], day)
            time.sleep(PAUSE)

            if obs is None:
                ok = False
                print(f"  MANQUANT: {name}")
                break

            core[name] = obs
            print(f"  OK {name}: {obs['debit_m3_s']:.3f} m3/s")

        if ok:
            return day, core

    raise RuntimeError(
        "Aucune date commune trouvee pour les 5 stations principales."
    )


def core_complete(results):
    return all(name in results for name in required_names())


def build_exutoires(results):
    exutoires = {}

    for name in DIRECT_EXUTOIRES:
        obs = results.get(name)

        if obs is None:
            continue

        q = obs["debit_m3_s"]

        exutoires[name] = {
            "type": "mesure_ou_reference",
            "debit_m3_s": round(q, 3),
            "volume_m3_jour": round(q * 86400),
            "stations": [name],
        }

    # Gironde : Garonne + Dordogne, sans les recompter ailleurs
    if "Garonne" in results and "Dordogne" in results:
        q = (
            results["Garonne"]["debit_m3_s"]
            + results["Dordogne"]["debit_m3_s"]
        )

        exutoires["Gironde"] = {
            "type": "reconstitue",
            "debit_m3_s": round(q, 3),
            "volume_m3_jour": round(q * 86400),
            "stations": ["Garonne", "Dordogne"],
            "note": "Garonne + Dordogne, sans double comptage.",
        }

    # Adour reconstitue
    if all(name in results for name in ADOUR_COMPONENTS):
        q = sum(
            results[name]["debit_m3_s"]
            for name in ADOUR_COMPONENTS
        )

        exutoires["Adour"] = {
            "type": "reconstitue",
            "debit_m3_s": round(q, 3),
            "volume_m3_jour": round(q * 86400),
            "stations": ADOUR_COMPONENTS,
            "note": (
                "Adour principal + Gave de Pau "
                "+ Gave d'Oloron + Nive."
            ),
        }

    return exutoires


def daily_summary(day, results):
    exutoires = build_exutoires(results)

    q = sum(
        item["debit_m3_s"]
        for item in exutoires.values()
    )

    volume = sum(
        item["volume_m3_jour"]
        for item in exutoires.values()
    )

    station_count = len(results)
    station_expected = len(STATIONS)

    exutoire_count = len(exutoires)
    exutoire_expected = len(DIRECT_EXUTOIRES) + 2

    return {
        "date": day.isoformat(),
        "debit_m3_s": round(q, 3),
        "volume_m3_jour": round(volume),

        "stations_disponibles": station_count,
        "stations_prevues": station_expected,

        "couverture_stations_pct": round(
            100 * station_count / station_expected,
            1,
        ),

        "exutoires_disponibles": exutoire_count,
        "exutoires_prevus": exutoire_expected,

        "couverture_exutoires_pct": round(
            100 * exutoire_count / exutoire_expected,
            1,
        ),

        "method_version": METHOD_VERSION,
    }


def hydro_start(day):
    year = day.year if day.month >= 9 else day.year - 1
    return date(year, 9, 1)


def load_history():
    rows = {}

    if not HISTORY_FILE.exists():
        return rows

    with HISTORY_FILE.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        for row in csv.DictReader(file):
            if row.get("date"):
                rows[row["date"]] = row

    return rows


def fill_missing_days(
    history,
    start_day,
    end_day,
    latest_day,
    latest_results,
):
    day = start_day

    while day <= end_day:
        key = day.isoformat()

        if key in history:
            day += timedelta(days=1)
            continue

        print("")
        print(f"Jour a completer: {day}")

        if day == latest_day:
            results = dict(latest_results)
        else:
            results = collect_day(day)

        if not core_complete(results):
            print(
                "  Jour ignore provisoirement: "
                "station principale manquante."
            )

            day += timedelta(days=1)
            continue

        summary = daily_summary(day, results)

        history[key] = {
            k: str(v)
            for k, v in summary.items()
        }

        day += timedelta(days=1)

    return history


def write_history(history, start_day, end_day):
    fields = [
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
        "cumul_volume_m3",
        "cumul_milliards_m3",
    ]

    rows = []

    for key, row in history.items():
        try:
            row_day = date.fromisoformat(key)
        except ValueError:
            continue

        if start_day <= row_day <= end_day:
            rows.append(dict(row))

    rows.sort(
        key=lambda row: row["date"]
    )

    cumul = 0

    for row in rows:
        try:
            volume = round(
                float(row.get("volume_m3_jour", 0))
            )
        except (TypeError, ValueError):
            volume = 0

        cumul += int(volume)

        row["cumul_volume_m3"] = str(cumul)

        row["cumul_milliards_m3"] = (
            f"{cumul / 1_000_000_000:.6f}"
        )

        for field in fields:
            row.setdefault(field, "")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with HISTORY_FILE.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    return rows


def cumulative_summary(rows, start_day, end_day):
    expected_days = (
        end_day - start_day
    ).days + 1

    covered_days = len(rows)

    volume = 0

    for row in rows:
        try:
            volume += round(
                float(
                    row.get(
                        "volume_m3_jour",
                        0,
                    )
                )
            )
        except (TypeError, ValueError):
            pass

    return {
        "date_debut": start_day.isoformat(),
        "date_fin": end_day.isoformat(),

        "jours_couverts": covered_days,
        "jours_attendus": expected_days,

        "couverture_jours_pct": round(
            100 * covered_days / expected_days,
            1,
        ),

        "volume_m3": int(volume),

        "volume_millions_m3": round(
            volume / 1_000_000,
            3,
        ),

        "volume_milliards_m3": round(
            volume / 1_000_000_000,
            6,
        ),
    }


def station_details(results):
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


def save_latest(day, results, cumul):
    exutoires = build_exutoires(results)
    summary = daily_summary(day, results)

    payload = {
        "date": day.isoformat(),

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

            "debit_m3_s":
                summary["debit_m3_s"],

            "volume_m3_jour":
                summary["volume_m3_jour"],

            "stations_disponibles":
                summary["stations_disponibles"],

            "stations_prevues":
                summary["stations_prevues"],

            "couverture_stations_pct":
                summary["couverture_stations_pct"],

            "exutoires_disponibles":
                summary["exutoires_disponibles"],

            "exutoires_prevus":
                summary["exutoires_prevus"],

            "couverture_exutoires_pct":
                summary["couverture_exutoires_pct"],
        },

        "cumul_hydrologique": cumul,

        "exutoires": exutoires,

        "stations": station_details(results),

        "avertissement": (
            "Version V1.2 de test. "
            "Le total et le cumul representent uniquement "
            "les flux mesures ou reconstitues du reseau V1. "
            "L'estimation des zones non jaugees "
            "n'est pas encore ajoutee."
        ),
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    return payload


def main():
    print(
        "=== COMPTEUR EAU DOUCE FRANCE - V1.2 TEST ==="
    )

    latest_day, core = latest_common_day()

    latest_results = collect_day(
        latest_day,
        core,
    )

    start_day = hydro_start(latest_day)

    history = load_history()

    # Toujours recalculer le dernier jour
    # avec la methode actuelle.
    history.pop(
        latest_day.isoformat(),
        None,
    )

    history = fill_missing_days(
        history,
        start_day,
        latest_day,
        latest_day,
        latest_results,
    )

    rows = write_history(
        history,
        start_day,
        latest_day,
    )

    cumul = cumulative_summary(
        rows,
        start_day,
        latest_day,
    )

    payload = save_latest(
        latest_day,
        latest_results,
        cumul,
    )

    print("")
    print(f"Date: {payload['date']}")

    print(
        "Debit V1: "
        f"{payload['total']['debit_m3_s']:.3f} m3/s"
    )

    print(
        "Volume jour: "
        f"{payload['total']['volume_m3_jour']:,} m3"
    )

    print(
        "Cumul depuis le 1er septembre: "
        f"{cumul['volume_m3']:,} m3"
    )

    print(
        "Soit: "
        f"{cumul['volume_milliards_m3']:.3f} "
        "milliard(s) de m3"
    )

    print(
        "Jours couverts: "
        f"{cumul['jours_couverts']}/"
        f"{cumul['jours_attendus']}"
    )

    print(
        "TEST: le compteur public actuel "
        "n'est pas modifie."
    )


if __name__ == "__main__":
    main()
