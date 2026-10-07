from __future__ import annotations

from collections import defaultdict

import requests
from elasticsearch import Elasticsearch, helpers


SOCRATA = "https://data.cityofnewyork.us/resource"
CLIMATE_INDEX = "carbon-copy-climate-signals-v1"


def _get(dataset: str, params: dict) -> list[dict]:
    response = requests.get(f"{SOCRATA}/{dataset}.json", params=params, timeout=45)
    response.raise_for_status()
    return response.json()


def fetch_climate_signals() -> tuple[list[dict], dict]:
    flood_rows = _get(
        "7n9x-tbtd",
        {
            "$select": "nta_code,nta_name,scenario_code,scenario_name,count",
            "$where": "scenario_code in ('1','3')",
            "$limit": 2000,
        },
    )
    flood_by_nta: dict[str, dict] = {}
    for row in flood_rows:
        item = flood_by_nta.setdefault(
            row["nta_code"],
            {"signal_type": "flood_exposure", "name": row["nta_name"], "nta_code": row["nta_code"]},
        )
        if row["scenario_code"] == "1":
            item["buildings_2020s"] = int(row["count"])
        elif row["scenario_code"] == "3":
            item["buildings_2050s"] = int(row["count"])
    flood_docs = []
    for item in flood_by_nta.values():
        current = item.get("buildings_2020s", 0)
        future = item.get("buildings_2050s", 0)
        item["additional_buildings"] = future - current
        item["percent_increase"] = round((future - current) / current * 100, 1) if current else None
        flood_docs.append(item)

    event_rows = _get(
        "aq7i-eu5q",
        {"$select": "sensor_name,sensor_id,max_depth_inches,duration_mins,flood_start_time", "$limit": 5000},
    )
    sensors: dict[str, dict] = defaultdict(
        lambda: {"events": 0, "max_depth_inches": 0.0, "longest_event_minutes": 0.0}
    )
    for row in event_rows:
        sensor = sensors[row["sensor_name"]]
        sensor["events"] += 1
        sensor["max_depth_inches"] = max(sensor["max_depth_inches"], float(row.get("max_depth_inches", 0)))
        sensor["longest_event_minutes"] = max(sensor["longest_event_minutes"], float(row.get("duration_mins", 0)))
    sensor_docs = [
        {"signal_type": "measured_flooding", "name": name, **values} for name, values in sensors.items()
    ]

    gi_rows = _get(
        "df32-vzax",
        {"$select": "status_gro,count(*) as count", "$group": "status_gro", "$limit": 100},
    )
    gi_docs = [
        {"signal_type": "green_infrastructure", "name": row.get("status_gro") or "Unknown", "count": int(row["count"])}
        for row in gi_rows
    ]

    air_rows = _get(
        "c3uy-2p5r",
        {
            "$select": "geo_place_name,time_period,start_date,data_value,measure_info",
            "$where": "name='Fine particles (PM 2.5)' AND geo_type_name='UHF42'",
            "$order": "start_date DESC",
            "$limit": 100,
        },
    )
    latest_period = air_rows[0]["time_period"] if air_rows else "Unavailable"
    latest_air = [row for row in air_rows if row["time_period"] == latest_period]
    air_docs = [
        {
            "signal_type": "air_quality",
            "name": row["geo_place_name"],
            "time_period": row["time_period"],
            "pm25": float(row["data_value"]),
            "units": row.get("measure_info", "mcg/m3"),
        }
        for row in latest_air
    ]

    top_flood_growth = sorted(flood_docs, key=lambda x: x["additional_buildings"], reverse=True)[:5]
    top_measured = sorted(sensor_docs, key=lambda x: (x["events"], x["max_depth_inches"]), reverse=True)[:5]
    worst_air = sorted(air_docs, key=lambda x: x["pm25"], reverse=True)[:5]
    gi_counts = {row["name"]: row["count"] for row in gi_docs}
    summary = {
        "top_flood_growth": top_flood_growth,
        "top_measured_flooding": top_measured,
        "worst_air": worst_air,
        "air_period": latest_period,
        "green_infrastructure": gi_counts,
        "flood_event_count": len(event_rows),
    }
    return [*flood_docs, *sensor_docs, *gi_docs, *air_docs], summary


def ensure_climate_signals(es: Elasticsearch) -> dict:
    if es.indices.exists(index=CLIMATE_INDEX) and es.count(index=CLIMATE_INDEX)["count"]:
        # Refresh the summaries from source; the index remains the searchable evidence store.
        _, summary = fetch_climate_signals()
        return summary
    docs, summary = fetch_climate_signals()
    es.indices.create(index=CLIMATE_INDEX)
    helpers.bulk(
        es,
        (
            {"_index": CLIMATE_INDEX, "_id": f"{doc['signal_type']}:{idx}", "_source": doc}
            for idx, doc in enumerate(docs)
        ),
    )
    es.indices.refresh(index=CLIMATE_INDEX)
    return summary
