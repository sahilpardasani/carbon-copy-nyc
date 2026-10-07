from __future__ import annotations

import html
import math
import os
import re
import json
from dataclasses import dataclass
from statistics import median
from typing import Any, Literal, TypeVar

import requests
from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
from mistralai import Mistral
from pydantic import BaseModel


DATASET_ID = "5zyy-y8am"
DATA_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
INDEX_NAME = "carbon-copy-buildings-v1"
REPORT_YEAR = 2024
PROPERTY_TYPE = "Multifamily Housing"
LL97_R2_LIMIT_KG_CO2E_FT2 = 6.75
LL97_PENALTY_PER_TON = 268.0
FIELDS = [
    "property_id",
    "property_name",
    "address_1",
    "borough",
    "postal_code",
    "primary_property_type",
    "property_gfa_calculated",
    "year_built",
    "site_eui_kbtu_ft",
    "total_location_based_ghg",
    "total_location_based_ghg_1",
    "energy_star_score",
    "latitude",
    "longitude",
    "report_year",
]


@dataclass(frozen=True)
class PeerResult:
    target: dict[str, Any]
    peers: list[dict[str, Any]]
    greener_twins: list[dict[str, Any]]
    peer_count: int
    median_intensity: float
    median_site_eui: float
    emissions_gap_tons: float
    percent_vs_median: float
    peer_definition: str
    ll97_screened_overage_tons: float
    ll97_screened_penalty: float


class AnalysisIntent(BaseModel):
    focus: Literal["peer_position", "emissions_gap", "greener_twins", "energy_use"]
    action: Literal["verify_ll97_exposure", "scope_energy_retrofit", "protect_peer_lead"]


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def load_settings() -> None:
    load_dotenv()
    missing = [
        key
        for key in ("ELASTIC_ENDPOINT", "ELASTIC_API_KEY", "MISTRAL_API_KEY")
        if not os.getenv(key)
    ]
    if missing:
        raise RuntimeError(f"Missing configuration: {', '.join(missing)}")


def elastic_client() -> Elasticsearch:
    load_settings()
    return Elasticsearch(
        os.environ["ELASTIC_ENDPOINT"],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=60,
    )


def mistral_client() -> Mistral:
    load_settings()
    return Mistral(api_key=os.environ["MISTRAL_API_KEY"])


def mistral_structured(
    schema: type[StructuredModel], messages: list[dict[str, str]], model: str | None = None
) -> StructuredModel:
    """Parse ML4 preview responses, which include separate reasoning and final-text chunks."""
    schema_prompt = (
        "Return only valid JSON matching this schema. Do not wrap it in Markdown: "
        + json.dumps(schema.model_json_schema())
    )
    response = mistral_client().chat.complete(
        model=model or os.getenv("MISTRAL_MODEL", "mistral-large-4"),
        messages=[*messages, {"role": "system", "content": schema_prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        top_p=1,
    )
    content = response.choices[0].message.content
    if isinstance(content, str):
        final_text = content
    else:
        final_text = "".join(
            chunk.text for chunk in content if getattr(chunk, "type", None) == "text" and getattr(chunk, "text", None)
        )
    if not final_text:
        raise ValueError("Mistral Large 4 returned no final JSON text")
    return schema.model_validate_json(final_text)


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if value in (None, "", "Not Available", "N/A"):
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return int(parsed) if integer else parsed
    except (TypeError, ValueError):
        return None


def normalize_building(raw: dict[str, Any]) -> dict[str, Any] | None:
    gfa = _number(raw.get("property_gfa_calculated"))
    intensity = _number(raw.get("total_location_based_ghg_1"))
    emissions = _number(raw.get("total_location_based_ghg"))
    site_eui = _number(raw.get("site_eui_kbtu_ft"))
    year_built = _number(raw.get("year_built"), integer=True)
    if not all((gfa, intensity, emissions, site_eui, year_built)):
        return None
    if gfa <= 0 or intensity <= 0 or emissions <= 0 or site_eui <= 0:
        return None

    lat = _number(raw.get("latitude"))
    lon = _number(raw.get("longitude"))
    doc: dict[str, Any] = {
        "property_id": str(raw["property_id"]),
        "property_name": html.unescape(raw.get("property_name") or "Unnamed building"),
        "address": html.unescape(raw.get("address_1") or "Address unavailable"),
        "borough": (raw.get("borough") or "UNKNOWN").title(),
        "postal_code": str(raw.get("postal_code") or ""),
        "property_type": raw.get("primary_property_type") or PROPERTY_TYPE,
        "floor_area_sqft": float(gfa),
        "year_built": int(year_built),
        "site_eui": float(site_eui),
        "total_ghg_tons": float(emissions),
        "ghg_intensity": float(intensity),
        "energy_star_score": _number(raw.get("energy_star_score"), integer=True),
        "report_year": int(_number(raw.get("report_year"), integer=True) or REPORT_YEAR),
        "search_text": " ".join(
            filter(
                None,
                [raw.get("property_name"), raw.get("address_1"), raw.get("borough"), raw.get("postal_code")],
            )
        ),
    }
    if lat is not None and lon is not None:
        doc["location"] = {"lat": float(lat), "lon": float(lon)}
    return doc


def fetch_buildings(limit: int = 15_000) -> list[dict[str, Any]]:
    where = (
        f"report_year='{REPORT_YEAR}' AND primary_property_type='{PROPERTY_TYPE}' "
        "AND property_gfa_calculated IS NOT NULL "
        "AND year_built IS NOT NULL "
        "AND site_eui_kbtu_ft IS NOT NULL "
        "AND total_location_based_ghg IS NOT NULL "
        "AND total_location_based_ghg_1 IS NOT NULL"
    )
    response = requests.get(
        DATA_URL,
        params={"$select": ",".join(FIELDS), "$where": where, "$limit": limit},
        timeout=90,
    )
    response.raise_for_status()
    return [doc for row in response.json() if (doc := normalize_building(row))]


def create_index(es: Elasticsearch) -> None:
    if es.indices.exists(index=INDEX_NAME):
        return
    es.indices.create(
        index=INDEX_NAME,
        mappings={
            "properties": {
                "property_id": {"type": "keyword"},
                "property_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "address": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "search_text": {"type": "text"},
                "borough": {"type": "keyword"},
                "postal_code": {"type": "keyword"},
                "property_type": {"type": "keyword"},
                "floor_area_sqft": {"type": "double"},
                "year_built": {"type": "integer"},
                "site_eui": {"type": "double"},
                "total_ghg_tons": {"type": "double"},
                "ghg_intensity": {"type": "double"},
                "energy_star_score": {"type": "integer"},
                "report_year": {"type": "integer"},
                "location": {"type": "geo_point"},
            }
        },
    )


def index_buildings(es: Elasticsearch, buildings: list[dict[str, Any]]) -> int:
    create_index(es)
    success, _ = helpers.bulk(
        es,
        ({"_index": INDEX_NAME, "_id": b["property_id"], "_source": b} for b in buildings),
        chunk_size=500,
        request_timeout=120,
    )
    es.indices.refresh(index=INDEX_NAME)
    return success


def ensure_data(es: Elasticsearch) -> int:
    if es.indices.exists(index=INDEX_NAME):
        count = int(es.count(index=INDEX_NAME)["count"])
        if count:
            return count
    return index_buildings(es, fetch_buildings())


def search_buildings(es: Elasticsearch, query: str, size: int = 10) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        response = es.search(
            index=INDEX_NAME,
            size=size,
            query={"match_all": {}},
            sort=[{"total_ghg_tons": "desc"}],
        )
    elif re.fullmatch(r"\d{5}", query):
        response = es.search(
            index=INDEX_NAME,
            size=size,
            query={"term": {"postal_code": query}},
            sort=[{"total_ghg_tons": "desc"}],
        )
    else:
        response = es.search(
            index=INDEX_NAME,
            size=size,
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["property_name^3", "address^4", "search_text", "postal_code^2"],
                    "fuzziness": "AUTO",
                }
            },
        )
    return [hit["_source"] for hit in response["hits"]["hits"]]


def find_peers(es: Elasticsearch, target: dict[str, Any], size: int = 100) -> PeerResult:
    area = target["floor_area_sqft"]
    built = target["year_built"]
    response = None
    selected_tolerance = None
    for area_tolerance, year_tolerance in ((0.25, 15), (0.50, 30), (0.75, 50)):
        filters = [
            {"term": {"property_type": target["property_type"]}},
            {"term": {"report_year": target["report_year"]}},
            {
                "range": {
                    "floor_area_sqft": {
                        "gte": area * (1 - area_tolerance),
                        "lte": area * (1 + area_tolerance),
                    }
                }
            },
            {"range": {"year_built": {"gte": max(1800, built - year_tolerance), "lte": built + year_tolerance}}},
        ]
        candidate = es.search(
            index=INDEX_NAME,
            size=size,
            query={
                "bool": {
                    "filter": filters,
                    "must_not": [{"term": {"property_id": target["property_id"]}}],
                }
            },
            sort=[{"ghg_intensity": "asc"}],
        )
        response = candidate
        selected_tolerance = (area_tolerance, year_tolerance)
        if int(candidate["hits"]["total"]["value"]) >= 3:
            break

    assert response is not None and selected_tolerance is not None
    peers = [hit["_source"] for hit in response["hits"]["hits"]]
    peer_count = int(response["hits"]["total"]["value"])
    if not peers:
        raise RuntimeError("No comparable buildings found for this property.")

    # Compute medians from returned peers too, so the result remains robust if an
    # Elasticsearch percentile approximation changes across versions.
    median_intensity = float(median(p["ghg_intensity"] for p in peers))
    median_site_eui = float(median(p["site_eui"] for p in peers))
    greener = [p for p in peers if p["ghg_intensity"] < target["ghg_intensity"]][:3]
    gap = (target["ghg_intensity"] - median_intensity) * area / 1000.0
    pct = (target["ghg_intensity"] / median_intensity - 1) * 100 if median_intensity else 0.0
    area_tolerance, year_tolerance = selected_tolerance
    peer_definition = (
        f"Same property type and report year; floor area ±{area_tolerance:.0%}; "
        f"year built ±{year_tolerance} years."
    )
    ll97_overage = max(
        0.0,
        (target["ghg_intensity"] - LL97_R2_LIMIT_KG_CO2E_FT2) * area / 1000.0,
    )
    return PeerResult(
        target=target,
        peers=peers,
        greener_twins=greener,
        peer_count=peer_count,
        median_intensity=median_intensity,
        median_site_eui=median_site_eui,
        emissions_gap_tons=gap,
        percent_vs_median=pct,
        peer_definition=peer_definition,
        ll97_screened_overage_tons=ll97_overage,
        ll97_screened_penalty=ll97_overage * LL97_PENALTY_PER_TON,
    )


def explain_with_mistral(result: PeerResult, question: str) -> str:
    twins = [
        {
            "name": b["property_name"],
            "address": b["address"],
            "year_built": b["year_built"],
            "floor_area_sqft": round(b["floor_area_sqft"]),
            "ghg_intensity_kg_co2e_ft2": b["ghg_intensity"],
            "site_eui_kbtu_ft2": b["site_eui"],
            "total_ghg_metric_tons": b["total_ghg_tons"],
        }
        for b in result.greener_twins
    ]
    evidence = {
        "target": {
            "name": result.target["property_name"],
            "address": result.target["address"],
            "year_built": result.target["year_built"],
            "floor_area_sqft": round(result.target["floor_area_sqft"]),
            "ghg_intensity_kg_co2e_ft2": result.target["ghg_intensity"],
            "site_eui_kbtu_ft2": result.target["site_eui"],
            "total_ghg_metric_tons": result.target["total_ghg_tons"],
        },
        "peer_definition": result.peer_definition,
        "peer_count": result.peer_count,
        "peer_median_ghg_intensity_kg_co2e_ft2": round(result.median_intensity, 2),
        "peer_median_site_eui_kbtu_ft2": round(result.median_site_eui, 1),
        "benchmark_emissions_gap_metric_tons": round(result.emissions_gap_tons, 1),
        "ll97_screen": {
            "r2_2024_2029_limit_kg_co2e_ft2": LL97_R2_LIMIT_KG_CO2E_FT2,
            "screened_overage_metric_tons": round(result.ll97_screened_overage_tons, 1),
            "maximum_penalty_rate_usd_per_ton": LL97_PENALTY_PER_TON,
            "screened_maximum_annual_penalty_usd": round(result.ll97_screened_penalty),
            "warning": "Screening proxy only. LL84 location-based emissions are not a certified LL97 calculation.",
        },
        "greener_twins": twins,
    }
    verified_briefing = evidence_fallback(result)
    prompt = f"""User question: {question}

Verified evidence from Elasticsearch and deterministic calculations:
{evidence}

Choose the single analysis focus that best answers the user's question:
- peer_position: how the target ranks against comparable buildings
- emissions_gap: the target's benchmark emissions gap
- greener_twins: examples of similar lower-emissions buildings
- energy_use: site energy use comparison

Also choose the most useful developer action:
- verify_ll97_exposure: obtain a certified LL97 calculation and compliance plan
- scope_energy_retrofit: scope efficiency, controls, envelope, or electrification work
- protect_peer_lead: preserve and monitor performance that is already ahead of peers

Return only the structured selection. Do not perform calculations."""
    parsed = mistral_structured(
        AnalysisIntent,
        [
            {
                "role": "system",
                "content": "You are Carbon Copy, an evidence-first NYC building emissions analyst.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    leads = {
        "peer_position": "Mistral identified the peer comparison as the clearest answer to this question.",
        "emissions_gap": "Mistral identified the benchmark emissions gap as the clearest answer to this question.",
        "greener_twins": "Mistral identified the lower-emissions peer examples as the clearest answer to this question.",
        "energy_use": "Mistral identified site energy use as the clearest answer to this question.",
    }
    return f"*{leads[parsed.focus]}*\n\n{verified_briefing}\n\n{developer_action(result, parsed.action)}"


def evidence_fallback(result: PeerResult) -> str:
    target = result.target
    twin_names = ", ".join(b["property_name"] for b in result.greener_twins)
    if result.percent_vs_median >= 0:
        comparison = (
            f"**What this means:** {target['property_name']} produces about "
            f"**{result.percent_vs_median:.0f}% more climate pollution per square foot** than a typical similar building."
        )
        gap = (
            f"If it performed like the middle of its peer group, annual emissions would be about "
            f"**{result.emissions_gap_tons:,.1f} metric tons lower**. That is a comparison target, not a promised saving."
        )
    else:
        comparison = (
            f"**What this means:** {target['property_name']} produces about "
            f"**{abs(result.percent_vs_median):.0f}% less climate pollution per square foot** than a typical similar building."
        )
        gap = (
            f"It is already ahead of the peer benchmark by about "
            f"**{abs(result.emissions_gap_tons):,.1f} metric tons per year** at its reported size."
        )
    twins = (
        f"**Proof that better performance is possible:** comparable lower-emissions buildings include {twin_names}."
        if twin_names
        else "This building is already the lowest-emissions property in its matched peer set."
    )
    caveat = (
        f"Carbon Copy compared it with **{result.peer_count:,} buildings** of the same type and reporting year, "
        f"using similar size and construction age."
    )
    return "\n\n".join([comparison, gap, twins, caveat])


def developer_action(result: PeerResult, action: str = "verify_ll97_exposure") -> str:
    if result.ll97_screened_overage_tons > 0:
        economics = (
            f"Using the reported LL84 location-based intensity as a rough screen, this property is "
            f"**{result.ll97_screened_overage_tons:,.1f} metric tons CO₂e above** the current "
            f"multifamily R-2 limit. At the statutory maximum rate of **$268 per excess ton**, "
            f"that represents up to **${result.ll97_screened_penalty:,.0f} per year** of potential "
            "penalty exposure."
        )
        benefit = (
            "Reducing verified emissions can lower that exposure while also reducing energy and "
            "maintenance costs; incentives and financing can reduce upfront retrofit cost."
        )
    else:
        economics = (
            "This reported intensity is below the current multifamily R-2 screening limit, so this "
            "proxy does not indicate an emissions overage."
        )
        benefit = (
            "Maintaining that performance can protect compliance headroom, operating efficiency, "
            "resident comfort, and the property's marketability."
        )

    action_text = {
        "verify_ll97_exposure": (
            "**Action:** Ask the free NYC Accelerator program for a building-specific LL97 compliance "
            "calculation, retrofit scope, incentive search, and financing plan."
        ),
        "scope_energy_retrofit": (
            "**Action:** Commission an energy audit and have NYC Accelerator scope building controls, "
            "commissioning, envelope improvements, and electrification options against the verified emissions profile."
        ),
        "protect_peer_lead": (
            "**Action:** Establish ongoing energy monitoring and preventive maintenance, then use NYC "
            "Accelerator to identify incentives that preserve or extend the building's peer advantage."
        ),
    }.get(action, "**Action:** Obtain a certified LL97 assessment through NYC Accelerator.")

    caveat = (
        "*Economic screen only: actual LL97 applicability, emissions, limits, deductions, adjustments, "
        "and penalties require DOB records and a registered design professional.*"
    )
    sources = (
        "[NYC Local Law 97](https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page) · "
        "[NYC Accelerator](https://www.nyc.gov/site/nycaccelerator/index.page) · "
        "[NYSERDA multifamily programs](https://www.nyserda.ny.gov/All-Programs/Multifamily-Building-Programs)"
    )
    return "\n\n".join(["### What the owner or developer should do next", action_text, f"**Why it matters financially:** {economics}", benefit, caveat, sources])


def _numeric_tokens(text: str) -> set[str]:
    return {token.replace(",", "") for token in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def format_number(value: float) -> str:
    if not math.isfinite(value):
        return "—"
    return f"{value:,.1f}"
