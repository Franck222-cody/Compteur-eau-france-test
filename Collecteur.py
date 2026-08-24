#!/usr/bin/env python3
import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATION = "H320000104"
STATION_NAME = "Seine à Vernon"
BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"

def fetch_qmj(day):
    params = {
        "code_entite": STATION,
        "date_debut_obs_elab": day.isoformat(),
        "date_fin_obs_elab": day.isoformat(),
        "grandeur_hydro_elab": "QmnJ",
        "size": 20,
    }

    url = BASE_URL + "?" + urlencode(params)
    req = Request(
        url,
        headers={"User-Agent": "Compteur-Eau-Douce-France-V1/0.1"}
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
        "date": day.isoformat(),
        "station": STATION,
        "nom": STATION_NAME,
        "qmj_m3_s": round(q_m3_s, 3),
        "volume_m3_jour": round(volume_m3, 0),
        "volume_millions_m3_jour": round(volume_m3 / 1_000_000, 3),
    }

today = date.today()
result = None

for n in range(1, 8):
    result = fetch_qmj(today - timedelta(days=n))
    if result:
        break

if not result:
    raise SystemExit("Aucun QmJ disponible sur les 7 derniers jours.")

print(json.dumps(result, ensure_ascii=False, indent=2))
