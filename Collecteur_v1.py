#!/usr/bin/env python3
import csv,json,time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

URL="https://hubeau.eaufrance.fr/api/v2/hydrometrie/obs_elab"
VERSION="V1.3-test"
OUT=Path("data_v1")
LATEST=OUT/"latest_v1.json"
HISTORY=OUT/"historique_v1.csv"

CODES={
"Seine":"H320000104","Loire":"M530001010","Rhone":"V720001002",
"Garonne":"O900001002","Dordogne":"P555001001",
"Adour_principal":"Q312001002","Gave_de_Pau":"Q523101001",
"Gave_Oloron":"Q741291001","Nive":"Q931251001",
"Charente":"R520001001","Vilaine":"J790061002","Somme":"E647091003",
"Orne":"I353101001","Vire":"I522101001","Sienne":"I711101001",
"Selune":"I922102001","Aude":"Y142201002","Herault":"Y237002001",
"Orb":"Y258002002","Aulne":"J381181001","Blavet":"J571211005",
"Odet":"J421191001","Elorn":"J340301001","Trieux":"J171171001",
"Leguer":"J223302001","Scorff":"J510221001","Rance":"J061161001"}

CORE=["Seine","Loire","Rhone","Garonne","Dordogne"]

DIRECT=["Seine","Loire","Rhone","Charente","Vilaine","Somme","Orne","Vire",
"Sienne","Selune","Aude","Herault","Orb","Aulne","Blavet","Odet","Elorn",
"Trieux","Leguer","Scorff","Rance"]

ADOUR=["Adour_principal","Gave_de_Pau","Gave_Oloron","Nive"]
EXPECTED=DIRECT+["Gironde","Adour"]

def fetch(code,day):
    p={
        "code_entite":code,
        "date_debut_obs_elab":day.isoformat(),
        "date_fin_obs_elab":day.isoformat(),
        "grandeur_hydro_elab":"QmnJ",
        "size":20
    }
    try:
        req=Request(
            URL+"?"+urlencode(p),
            headers={"User-Agent":"Compteur-Eau-V1.3"}
        )
        with urlopen(req,timeout=30) as r:
            rows=json.load(r).get("data",[])
    except Exception as e:
        print("API",code,e)
        return None

    for row in rows:
        v=row.get("resultat_obs_elab")
        if v is not None:
            try:
                return float(v)/1000
            except (TypeError,ValueError):
                pass
    return None

def collect(day,initial=None):
    res=dict(initial or {})
    for n,c in CODES.items():
        if n in res:
            continue
        q=fetch(c,day)
        time.sleep(.05)
        if q is None:
            print("MANQUANT:",n)
        else:
            res[n]=q
    return res

def latest_day():
    y=date.today()-timedelta(days=1)

    for off in range(11):
        d=y-timedelta(days=off)
        core={}

        for n in CORE:
            q=fetch(CODES[n],d)
            time.sleep(.05)

            if q is None:
                break

            core[n]=q

        if len(core)==len(CORE):
            return d,core

    raise RuntimeError(
        "Pas de date commune pour les 5 stations principales"
    )

def exutoires(res):
    ex={}

    for n in DIRECT:
        if n in res:
            ex[n]=res[n]

    if "Garonne" in res and "Dordogne" in res:
        ex["Gironde"]=res["Garonne"]+res["Dordogne"]

    if all(n in res for n in ADOUR):
        ex["Adour"]=sum(res[n] for n in ADOUR)

    return ex

def summary(day,res):
    ex=exutoires(res)

    ms=[n for n in CODES if n not in res]
    me=[n for n in EXPECTED if n not in ex]

    q=sum(ex.values())

    return {
        "date":day.isoformat(),
        "debit_m3_s":round(q,3),
        "volume_m3_jour":round(q*86400),

        "stations_disponibles":len(res),
        "stations_prevues":len(CODES),
        "couverture_stations_pct":
            round(100*len(res)/len(CODES),1),
        "stations_manquantes":";".join(ms),

        "exutoires_disponibles":len(ex),
        "exutoires_prevus":len(EXPECTED),
        "couverture_exutoires_pct":
            round(100*len(ex)/len(EXPECTED),1),
        "exutoires_manquants":";".join(me),

        "method_version":VERSION
    }

def hydro_start(day):
    return date(
        day.year if day.month>=9 else day.year-1,
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
            r["date"]:r
            for r in csv.DictReader(f)
            if r.get("date")
        }

FIELDS=[
"date","debit_m3_s","volume_m3_jour",
"stations_disponibles","stations_prevues",
"couverture_stations_pct","stations_manquantes",
"exutoires_disponibles","exutoires_prevus",
"couverture_exutoires_pct","exutoires_manquants",
"method_version","cumul_volume_m3","cumul_milliards_m3"
]

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
        cumul+=round(
            float(r.get("volume_m3_jour",0) or 0)
        )

        r["cumul_volume_m3"]=str(cumul)
        r["cumul_milliards_m3"]=f"{cumul/1e9:.6f}"

        for f in FIELDS:
            r.setdefault(f,"")

    OUT.mkdir(parents=True,exist_ok=True)

    with HISTORY.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:
        w=csv.DictWriter(
            f,
            fieldnames=FIELDS,
            extrasaction="ignore"
        )
        w.writeheader()
        w.writerows(rows)

    return rows,cumul

def save_latest(day,res,rows,cumul,start):
    s=summary(day,res)
    ex=exutoires(res)
    expected=(day-start).days+1

    payload={
        "date":day.isoformat(),
        "generated_at":
            datetime.now(timezone.utc).isoformat(),
        "method_version":VERSION,

        "total":{
            "type":"mesure_reconstituee",
            "debit_m3_s":s["debit_m3_s"],
            "volume_m3_jour":s["volume_m3_jour"],

            "stations_disponibles":
                s["stations_disponibles"],
            "stations_prevues":
                s["stations_prevues"],
            "couverture_stations_pct":
                s["couverture_stations_pct"],
            "stations_manquantes":[
                x for x in
                s["stations_manquantes"].split(";")
                if x
            ],

            "exutoires_disponibles":
                s["exutoires_disponibles"],
            "exutoires_prevus":
                s["exutoires_prevus"],
            "couverture_exutoires_pct":
                s["couverture_exutoires_pct"],
            "exutoires_manquants":[
                x for x in
                s["exutoires_manquants"].split(";")
                if x
            ]
        },

        "cumul_hydrologique":{
            "date_debut":start.isoformat(),
            "date_fin":day.isoformat(),
            "jours_couverts":len(rows),
            "jours_attendus":expected,
            "couverture_jours_pct":
                round(100*len(rows)/expected,1),
            "volume_m3":int(cumul),
            "volume_millions_m3":
                round(cumul/1e6,3),
            "volume_milliards_m3":
                round(cumul/1e9,6)
        },

        "exutoires":{
            n:{
                "debit_m3_s":round(q,3),
                "volume_m3_jour":round(q*86400)
            }
            for n,q in ex.items()
        },

        "avertissement":
            "V1.3 test - zones non jaugees non ajoutees."
    }

    with LATEST.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )

    return payload

def main():
    print("=== V1.3 TEST ===")

    last,core=latest_day()
    last_res=collect(last,core)
    start=hydro_start(last)

    h=load_history()

    if h and any(
        r.get("method_version")!=VERSION
        for r in h.values()
    ):
        print("Reconstruction historique V1.3")
        h={}

    h.pop(last.isoformat(),None)

    d=start

    while d<=last:
        k=d.isoformat()

        if k not in h:
            res=(
                last_res
                if d==last
                else collect(d)
            )

            if all(n in res for n in CORE):
                s=summary(d,res)

                h[k]={
                    a:str(b)
                    for a,b in s.items()
                }

                print(
                    d,
                    "stations:",
                    s["stations_manquantes"]
                    or "aucune",
                    "| exutoires:",
                    s["exutoires_manquants"]
                    or "aucun"
                )
            else:
                print(
                    d,
                    "ignore: station principale manquante"
                )

        d+=timedelta(days=1)

    rows,cumul=write_history(
        h,
        start,
        last
    )

    p=save_latest(
        last,
        last_res,
        rows,
        cumul,
        start
    )

    c=p["cumul_hydrologique"]

    print(
        "Date:",
        p["date"],
        "Debit:",
        p["total"]["debit_m3_s"],
        "m3/s"
    )

    print(
        "Cumul:",
        c["volume_m3"],
        "m3 Jours:",
        c["jours_couverts"],
        "/",
        c["jours_attendus"]
    )

    print(
        "TEST: compteur public non modifie"
    )

if __name__=="__main__":
    main()
