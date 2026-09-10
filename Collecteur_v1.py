#!/usr/bin/env python3
import csv, json, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"
VERSION = "V1.5-test"
OUT = Path("data_v1")
LATEST = OUT / "latest_v1.json"
HISTORY = OUT / "historique_v1.csv"

CODES = {
    "Seine":"H320000104","Loire":"M530001010","Rhone":"V720001002",
    "Garonne":"O900001002","Dordogne":"P555001001",
    "Adour_principal":"Q312001002","Gave_de_Pau":"Q523101001",
    "Gave_Oloron":"Q741291001","Nive":"Q931251001",
    "Charente":"R520001001","Vilaine":"J790061002","Somme":"E647091003",
    "Orne":"I353101001","Vire":"I522101001","Sienne":"I711101001",
    "Selune":"I922102001","Aude":"Y142201002","Herault":"Y237002001",
    "Orb":"Y258002002","Aulne":"J381181001","Blavet":"J571211005",
    "Odet":"J421191001","Elorn":"J340301001","Trieux":"J171171001",
    "Leguer":"J223302001","Scorff":"J510221001","Rance":"J061161001"
}

CORE = ["Seine","Loire","Rhone","Garonne","Dordogne"]

DIRECT = [
    "Seine","Loire","Rhone","Charente","Vilaine","Somme","Orne","Vire",
    "Sienne","Selune","Aude","Herault","Orb","Aulne","Blavet","Odet",
    "Elorn","Trieux","Leguer","Scorff","Rance"
]

ADOUR = ["Adour_principal","Gave_de_Pau","Gave_Oloron","Nive"]
EXPECTED = DIRECT + ["Gironde","Adour"]


def fetch_once(code, day):
    p = {
        "code_entite": code,
        "date_debut_obs_elab": day.isoformat(),
        "date_fin_obs_elab": day.isoformat(),
        "grandeur_hydro_elab": "QmnJ",
        "size": 20,
    }

    try:
        req = Request(
            URL + "?" + urlencode(p),
            headers={"User-Agent":"Compteur-Eau-V1.4"}
        )

        with urlopen(req, timeout=30) as r:
            rows = json.load(r).get("data", [])

    except Exception as e:
        print("API", code, e)
        return None

    for row in rows:
        v = row.get("resultat_obs_elab")

        if v is not None:
            try:
                return float(v) / 1000.0
            except (TypeError, ValueError):
                pass

    return None
    
def fetch(code, day):
    for tentative in range(3):
        q = fetch_once(code, day)

        if q is not None:
            return q

        if tentative < 2:
            print("Nouvelle tentative:", code, day)
            time.sleep(1)

    return None


def collect(day, initial=None):
    res = dict(initial or {})

    for name, code in CODES.items():

        if name in res:
            continue

        q = fetch(code, day)
        time.sleep(0.05)

        if q is None:
            print("MANQUANT:", day, name)
        else:
            res[name] = q

    return res


def latest_day():
    yesterday = date.today() - timedelta(days=1)

    for off in range(11):
        day = yesterday - timedelta(days=off)
        core = {}

        for name in CORE:
            q = fetch(CODES[name], day)
            time.sleep(0.05)

            if q is None:
                break

            core[name] = q

        if len(core) == len(CORE):
            return day, core

    raise RuntimeError(
        "Pas de date commune pour les 5 stations principales"
    )


def interpolate_missing(day, res):
    interp = []

    missing_before = [
        n for n in CODES
        if n not in res
    ]

    for name in missing_before:

        q_prev = fetch(
            CODES[name],
            day - timedelta(days=1)
        )
        time.sleep(0.05)

        q_next = fetch(
            CODES[name],
            day + timedelta(days=1)
        )
        time.sleep(0.05)

        if q_prev is not None and q_next is not None:

            res[name] = (
                q_prev + q_next
            ) / 2.0

            interp.append(name)

            print(
                "INTERPOLE:",
                day,
                name,
                res[name]
            )

    return res, interp


def exutoires(res):
    ex = {
        n: res[n]
        for n in DIRECT
        if n in res
    }

    if (
        "Garonne" in res
        and "Dordogne" in res
    ):
        ex["Gironde"] = (
            res["Garonne"]
            + res["Dordogne"]
        )

    if all(
        n in res
        for n in ADOUR
    ):
        ex["Adour"] = sum(
            res[n]
            for n in ADOUR
        )

    return ex


def exutoires_interpoles(interp):
    out = [
        n for n in DIRECT
        if n in interp
    ]

    if (
        "Garonne" in interp
        or "Dordogne" in interp
    ):
        out.append("Gironde")

    if any(
        n in interp
        for n in ADOUR
    ):
        out.append("Adour")

    return out


def summary(day, res, interp):
    ex = exutoires(res)

    ms = [
        n for n in CODES
        if n not in res
    ]

    me = [
        n for n in EXPECTED
        if n not in ex
    ]

    ei = exutoires_interpoles(
        interp
    )

    q = sum(
        ex.values()
    )

    return {
        "date":
            day.isoformat(),

        "debit_m3_s":
            round(q, 3),

        "volume_m3_jour":
            round(q * 86400),

        "stations_disponibles":
            len(res),

        "stations_prevues":
            len(CODES),

        "couverture_stations_pct":
            round(
                100 * len(res) / len(CODES),
                1
            ),

        "stations_interpolees":
            ";".join(interp),

        "stations_manquantes":
            ";".join(ms),

        "exutoires_disponibles":
            len(ex),

        "exutoires_prevus":
            len(EXPECTED),

        "couverture_exutoires_pct":
            round(
                100 * len(ex) / len(EXPECTED),
                1
            ),

        "exutoires_avec_interpolation":
            ";".join(ei),

        "exutoires_manquants":
            ";".join(me),

        "method_version":
            VERSION,
    }


def hydro_start(day):
    return date(
        day.year
        if day.month >= 9
        else day.year - 1,
        9,
        1
    )


def load_history():
    if not HISTORY.exists():
        return {}

    with HISTORY.open(
        encoding="utf-8",
        newline=""
    ) as f:

        return {
            r["date"]: r
            for r in csv.DictReader(f)
            if r.get("date")
        }


FIELDS = [
    "date",
    "debit_m3_s",
    "volume_m3_jour",
    "stations_disponibles",
    "stations_prevues",
    "couverture_stations_pct",
    "stations_interpolees",
    "stations_manquantes",
    "exutoires_disponibles",
    "exutoires_prevus",
    "couverture_exutoires_pct",
    "exutoires_avec_interpolation",
    "exutoires_manquants",
    "method_version",
    "cumul_volume_m3",
    "cumul_milliards_m3"
]


def rebuild_day(day, initial=None):
    res = collect(
        day,
        initial
    )

    res, interp = interpolate_missing(
        day,
        res
    )

    if not all(
        n in res
        for n in CORE
    ):
        print(
            day,
            "ignore: station principale toujours manquante"
        )
        return None

    s = summary(
        day,
        res,
        interp
    )

    print(
        day,
        "interp:",["stations_interpolees"] or "aucune",
        "| manque:",
        s["stations_manquantes"] or "aucun"
    )
    return s


def write_history(h,start,end):
    rows=[]
    for k,r in h.items():
        try:
            d=date.fromisoformat(k)
        except ValueError:
            continue
        if start<=d<=end:
            rows.append(dict(r))

    rows.sort(key=lambda r:r["date"])
    cumul=0

    for r in rows:
        cumul+=round(float(r.get("volume_m3_jour",0) or 0))
        r["cumul_volume_m3"]=str(cumul)
        r["cumul_milliards_m3"]=f"{cumul/1e9:.6f}"
        for f in FIELDS:
            r.setdefault(f,"")

    OUT.mkdir(parents=True,exist_ok=True)

    with HISTORY.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    return rows,cumul


def as_list(text):
    return [x for x in text.split(";") if x]


def save_latest(day,res,interp,rows,cumul,start):
    s=summary(day,res,interp)
    ex=exutoires(res)
    expected=(day-start).days+1

    payload={
        "date":day.isoformat(),
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "method_version":VERSION,

        "interpolation":{
            "methode":"moyenne J-1 / J+1",
            "usage":"trou isole seulement"
        },

        "total":{
            "type":"mesure_reconstituee",
            "debit_m3_s":s["debit_m3_s"],
            "volume_m3_jour":s["volume_m3_jour"],
            "stations_disponibles":s["stations_disponibles"],
            "stations_prevues":s["stations_prevues"],
            "couverture_stations_pct":s["couverture_stations_pct"],
            "stations_interpolees":as_list(s["stations_interpolees"]),
            "stations_manquantes":as_list(s["stations_manquantes"]),
            "exutoires_disponibles":s["exutoires_disponibles"],
            "exutoires_prevus":s["exutoires_prevus"],
            "couverture_exutoires_pct":s["couverture_exutoires_pct"],
            "exutoires_avec_interpolation":
                as_list(s["exutoires_avec_interpolation"]),
            "exutoires_manquants":as_list(s["exutoires_manquants"])
        },

        "cumul_hydrologique":{
            "date_debut":start.isoformat(),
            "date_fin":day.isoformat(),
            "jours_couverts":len(rows),
            "jours_attendus":expected,
            "couverture_jours_pct":round(100*len(rows)/expected,1),
            "volume_m3":int(cumul),
            "volume_millions_m3":round(cumul/1e6,3),
            "volume_milliards_m3":round(cumul/1e9,6)
        },

        "exutoires":{
            n:{
                "debit_m3_s":round(q,3),
                "volume_m3_jour":round(q*86400)
            }
            for n,q in ex.items()
        },

        "avertissement":
            "V1.4 test. Interpolations tracees. Zones non jaugees non ajoutees."
    }

    with LATEST.open("w",encoding="utf-8") as f:
        json.dump(payload,f,ensure_ascii=False,indent=2)


def main():
    print("=== V1.4 TEST ===")

    last,core=latest_day()
    last_res=collect(last,core)
    last_res,last_interp=interpolate_missing(last,last_res)
    start=hydro_start(last)
    h=load_history()

    if h and any(r.get("method_version")!=VERSION for r in h.values()):
        h={}

    d=start
    while d<=last:
        key=d.isoformat()

        redo=(
            key not in h
            or h[key].get("stations_manquantes")
            or h[key].get("stations_interpolees")
            or h[key].get("method_version")!=VERSION
            or d==last
        )

        if redo:
            s=rebuild_day(d,core if d==last else None)
            if s is not None:
                h[key]={k:str(v) for k,v in s.items()}

        d+=timedelta(days=1)

    rows,cumul=write_history(h,start,last)
    save_latest(last,last_res,last_interp,rows,cumul,start)

    print("Date:",last)
    print("Cumul:",cumul,"m3")
    print("Jours:",len(rows),"/",(last-start).days+1)
    print("TEST: compteur public non modifie")


if __name__=="__main__":
    main()
        
