#!/usr/bin/env python3

import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"

STATIONS = {
    "Seine": {
        "code": "H320000104",
        "nom": "Seine à Vernon"
    },
    "Loire": {
        "code": "M530001010",
        "nom": "Loire à Montjean-sur-Loire"
    },
    "Rhone": {
        "code": "V720001002",
        "nom": "Rhône à Tarascon"
    },
    "Garonne": {
        "code": "O900001002",
        "nom": "Garonne à Tonneins"
    },
    "Dordogne": {
        "code": "P555001001",
        "nom": "Dordogne à Pessac-sur-Dordogne"
    }
}


def fetch_qmj(code, day):
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
            "User-Agent": "Compteur-Eau-Douce-France-V1/0.2"
        }
    )

    with urlopen(req, timeout=30) as r:
        payload = json.load(r)

    rows = payload.get("data", [])

    if not rows:
        return None

    row = rows[0]

    q_l_s = row.get("resultat_obs_elab")

    if q_l_s is None:
        return None

    q_m3_s = float(q_l_s) / 1000.0
    volume_m3 = q_m3_s * 86400

    return {
        "qmj_m3_s": round(q_m3_s, 3),
        "volume_m3_jour": round(volume_m3, 0),
        "volume_millions_m3_jour": round(
            volume_m3 / 1_000_000, 3
        )
    }


today = date.today()

resultat_final = None

# On cherche une date commune disponible
# pour les 5 stations.
for n in range(1, 8):

    day = today - timedelta(days=n)

    stations_du_jour = {}
    tout_disponible = True

    for fleuve, info in STATIONS.items():

        valeur = fetch_qmj(info["code"], day)

        if valeur is None:
            tout_disponible = False
            break

        stations_du_jour[fleuve] = {
            "station": info["code"],
            "nom": info["nom"],
            **valeur
        }

    if tout_disponible:

        debit_total = sum(
            x["qmj_m3_s"]
            for x in stations_du_jour.values()
        )

        volume_total = sum(
            x["volume_m3_jour"]
            for x in stations_du_jour.values()
        )

        resultat_final = {
            "date": day.isoformat(),
            "nombre_stations": len(STATIONS),
            "stations": stations_du_jour,
            "total": {
                "debit_m3_s": round(debit_total, 3),
                "volume_m3_jour": round(volume_total, 0),
                "volume_millions_m3_jour": round(
                    volume_total / 1_000_000, 3
                )
            }
        }

        break


if resultat_final is None:
    raise SystemExit(
        "Aucune date commune disponible "
        "pour les 5 stations sur les 7 derniers jours."
    )


print(
    json.dumps(
        resultat_final,
        ensure_ascii=False,
        indent=2
    )
)
