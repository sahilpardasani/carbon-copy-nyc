from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bus_scenario import (
    DEFAULT_ELECTRIC_KWH_PER_MILE,
    DIESEL_GALLONS,
    DIESEL_MILES,
    NY_ELECTRIC_PRICE_PER_KWH,
    calculate_bus_scenario,
    fetch_diesel_prices,
    fetch_wti_prices,
)
from carbon_copy import INDEX_NAME, elastic_client, find_peers, search_buildings
from climate_signals import ensure_climate_signals
from executive_briefing import JAN_2026_DIESEL_AVG, SEP_2026_DIESEL_AVG, _dynamic_brief, _fallback_topic
from heat_priority import allocate_trees, ensure_heat_data, rank_neighborhoods

app = FastAPI(title="Carbon Copy NYC API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class BriefRequest(BaseModel):
    audience: str
    question: str


@lru_cache(maxsize=1)
def context() -> dict:
    es = elastic_client()
    ensure_heat_data(es)
    heat = allocate_trees(rank_neighborhoods(es, 50, 35, 15))
    climate = ensure_climate_signals(es)
    jan_bus = calculate_bus_scenario(JAN_2026_DIESEL_AVG)
    sep_bus = calculate_bus_scenario(SEP_2026_DIESEL_AVG)
    try:
        diesel_history = fetch_diesel_prices("2026-01-01")
        diesel_history = diesel_history[diesel_history["date"] <= "2026-09-30"]
        diesel_monthly = (
            diesel_history.assign(month=diesel_history["date"].dt.to_period("M"))
            .groupby("month", as_index=False)["diesel_price"].mean()
        )
        diesel_series = [
            {"month": row.month.strftime("%b"), "value": round(float(row.diesel_price), 3)}
            for row in diesel_monthly.itertuples()
        ]
    except Exception:
        diesel_series = [
            {"month": "Jan", "value": JAN_2026_DIESEL_AVG},
            {"month": "Sep", "value": SEP_2026_DIESEL_AVG},
        ]
    try:
        wti_history = fetch_wti_prices()
        wti_monthly = (
            wti_history.assign(month=wti_history["date"].dt.to_period("M"))
            .groupby("month", as_index=False)["wti_price"].mean()
        )
        wti_series = [
            {"month": row.month.strftime("%b"), "value": round(float(row.wti_price), 2)}
            for row in wti_monthly.itertuples()
        ]
    except Exception:
        wti_series = [
            {"month": "Jan", "value": 59.66},
            {"month": "Sep", "value": 96.84},
        ]
    evidence = {
        "BUS_COST_JAN": "At the January 2026 U.S. diesel average, modeled electric energy cost is $56.4 million lower per year than diesel.",
        "BUS_COST_SEP": "At the September 2026 U.S. diesel average, modeled electric energy cost is $166.1 million lower per year than diesel.",
        "BUS_PRICE_EXPOSURE": "The September modeled energy advantage is $109.7 million larger than January's because diesel was more expensive.",
        "BUS_POLLUTION": "Modeled operational reduction is 301,516 metric tons of heat-trapping pollution per year, about 0.6% of NYC's roughly 51 million metric tons reported citywide for 2021.",
        "OIL_PRICE": "WTI crude averaged $59.66 per barrel in January 2026 and $96.84 in September 2026; the data do not establish the cause.",
        "BUS_SCOPE": "The model uses FY2024 reported diesel bus travel and excludes buses, chargers, depots, financing, maintenance, batteries, and demand charges.",
        "MTA_AUTHORITY": "MTA is a New York State authority. City Hall can convene, coordinate city approvals, request evidence, and advocate, but cannot order the conversion alone.",
        "BUS_DECISION_DATA": "A decision-ready plan needs depot sequence, full ownership cost, utility and charger plan, cost per mile, charger uptime, missed service, energy use, and pollution per mile.",
        "TREE_METHOD": "The 100-tree planning allocation weights danger during heat waves at 50%, lack of vegetation at 35%, and limited home AC access at 15%.",
        "TREE_TOP": "; ".join(f"{row['neighborhood']}: {row['trees']} trees" for row in heat[:5]),
        "TREE_LIMIT": "Neighborhood ranking is not an exact planting-site plan; utilities, sidewalk space, ownership, species fit, and maintenance need field checks.",
        "BUILDING_DATA": "Carbon Copy indexes 14,281 NYC multifamily disclosure records and compares each property with similar peers.",
        "BUILDING_LIMIT": "Peer comparison is a screening signal, not an engineering forecast or legal Local Law 97 determination.",
        "FLOOD_EXPOSURE": "; ".join(
            f"{row['name']}: {row['buildings_2020s']} buildings in the 2020s flood zone, {row['buildings_2050s']} in the 2050s, increase {row['additional_buildings']}"
            for row in climate["top_flood_growth"]
        ),
        "FLOODNET_EVENTS": f"FloodNet contains {climate['flood_event_count']} quality-controlled measured flood events. "
        + "; ".join(
            f"{row['name']}: {row['events']} events, maximum depth {row['max_depth_inches']:.1f} inches"
            for row in climate["top_measured_flooding"]
        ),
        "GREEN_INFRASTRUCTURE": "; ".join(
            f"{status}: {count} DEP green-infrastructure assets" for status, count in climate["green_infrastructure"].items()
        ),
        "AIR_QUALITY": f"Latest neighborhood PM2.5 period is {climate['air_period']}. Highest measurements: "
        + "; ".join(f"{row['name']}: {row['pm25']} {row['units']}" for row in climate["worst_air"]),
        "CLIMATE_SIGNAL_LIMITS": "Flood exposure is a planning scenario, FloodNet only represents instrumented locations, green-infrastructure counts do not prove flood prevention, and neighborhood air quality does not identify an individual person's exposure.",
    }
    return {"climate": climate, "heat": heat, "jan_bus": jan_bus, "sep_bus": sep_bus, "diesel_series": diesel_series, "wti_series": wti_series, "evidence": evidence}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": "mistral-large-4"}


@app.get("/api/overview")
def overview() -> dict:
    ctx = context()
    climate = ctx["climate"]
    return {
        "metrics": {
            "buildings_indexed": 14281,
            "floodnet_events": climate["flood_event_count"],
            "green_infrastructure": climate["green_infrastructure"].get("Constructed", 0),
            "bus_pollution_reduction": round(ctx["sep_bus"].operational_co2_change_tons),
        },
        "flood_growth": climate["top_flood_growth"],
        "tree_priorities": ctx["heat"][:5],
        "air_quality": climate["worst_air"],
        "air_period": climate["air_period"],
        "bus_scenario": {
            "diesel_gallons": DIESEL_GALLONS,
            "diesel_miles": DIESEL_MILES,
            "electric_kwh_per_mile": DEFAULT_ELECTRIC_KWH_PER_MILE,
            "electricity_price": NY_ELECTRIC_PRICE_PER_KWH,
            "electric_kwh": ctx["sep_bus"].electric_kwh,
            "co2_reduction_tons": ctx["sep_bus"].operational_co2_change_tons,
            "january_diesel_price": JAN_2026_DIESEL_AVG,
            "september_diesel_price": SEP_2026_DIESEL_AVG,
            "diesel_history": ctx["diesel_series"],
            "wti_history": ctx["wti_series"],
        },
    }


@app.post("/api/brief")
def brief(request: BriefRequest) -> dict:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Please enter a policy question.")
    try:
        ctx = context()
        result = _dynamic_brief(request.question.strip(), request.audience, _fallback_topic(request.question), ctx["evidence"])
        return result.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Mistral briefing failed evidence validation: {exc}") from exc


@app.get("/api/trees")
def trees(
    vulnerability: int = Query(50, ge=0, le=100),
    vegetation: int = Query(35, ge=0, le=100),
    ac_access: int = Query(15, ge=0, le=100),
) -> dict:
    if vulnerability + vegetation + ac_access == 0:
        raise HTTPException(status_code=400, detail="At least one priority weight must be above zero.")
    es = elastic_client()
    rows = allocate_trees(rank_neighborhoods(es, vulnerability, vegetation, ac_access, size=10))
    return {"weights": {"vulnerability": vulnerability, "vegetation": vegetation, "ac_access": ac_access}, "neighborhoods": rows}


@app.get("/api/buildings/search")
def building_search(q: str = Query("", max_length=120)) -> dict:
    es = elastic_client()
    matches = search_buildings(es, q, size=8)
    return {"results": matches}


@app.get("/api/buildings/{property_id}/peers")
def building_peers(property_id: str) -> dict:
    es = elastic_client()
    try:
        target = es.get(index=INDEX_NAME, id=property_id)["_source"]
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Building not found.") from exc
    result = find_peers(es, target)
    return {
        "target": result.target,
        "greener_twins": result.greener_twins,
        "peer_count": result.peer_count,
        "median_intensity": result.median_intensity,
        "median_site_eui": result.median_site_eui,
        "emissions_gap_tons": result.emissions_gap_tons,
        "percent_vs_median": result.percent_vs_median,
        "peer_definition": result.peer_definition,
        "ll97_screened_penalty": result.ll97_screened_penalty,
    }
