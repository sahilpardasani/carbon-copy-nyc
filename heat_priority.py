from __future__ import annotations

import io
import json

import pandas as pd
import requests
from elasticsearch import Elasticsearch, helpers
from pydantic import BaseModel
from typing import Literal

from carbon_copy import mistral_structured


HVI_CSV_URL = (
    "https://a816-dohbesp.nyc.gov/IndicatorPublic/data-features/hvi/hvi-nta-2020.csv"
)
HEAT_INDEX = "carbon-copy-heat-priority-v1"


def fetch_heat_data() -> list[dict]:
    response = requests.get(HVI_CSV_URL, timeout=30)
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    records = []
    for row in frame.to_dict("records"):
        records.append(
            {
                "nta_code": str(row["NTACode"]),
                "neighborhood": str(row["GEONAME"]),
                "community_district": str(row["CDTACode"]),
                "borough": str(row["NTACode"])[:2],
                "hvi": int(row["HVI_RANK"]),
                "surface_temp_f": float(row["SURFACE_TEMP"]),
                "green_space_pct": float(row["GREENSPACE"]),
                "ac_access_pct": float(row["PCT_HOUSEHOLDS_AC"]),
                "median_income": float(row["MEDIAN_INCOME"]),
            }
        )
    return records


def ensure_heat_data(es: Elasticsearch) -> int:
    if es.indices.exists(index=HEAT_INDEX):
        count = int(es.count(index=HEAT_INDEX)["count"])
        if count:
            return count
    es.indices.create(
        index=HEAT_INDEX,
        mappings={
            "properties": {
                "nta_code": {"type": "keyword"},
                "neighborhood": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "community_district": {"type": "keyword"},
                "borough": {"type": "keyword"},
                "hvi": {"type": "integer"},
                "surface_temp_f": {"type": "double"},
                "green_space_pct": {"type": "double"},
                "ac_access_pct": {"type": "double"},
                "median_income": {"type": "double"},
            }
        },
    )
    records = fetch_heat_data()
    helpers.bulk(
        es,
        ({"_index": HEAT_INDEX, "_id": row["nta_code"], "_source": row} for row in records),
    )
    es.indices.refresh(index=HEAT_INDEX)
    return len(records)


def rank_neighborhoods(
    es: Elasticsearch,
    vulnerability_weight: int,
    vegetation_weight: int,
    ac_weight: int,
    size: int = 10,
) -> list[dict]:
    """Use Elasticsearch script scoring with normalized, visible policy weights."""
    response = es.search(
        index=HEAT_INDEX,
        size=size,
        query={
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": """
                        double hvi = (doc['hvi'].value - 1.0) / 4.0;
                        double greenDeficit = Math.max(0, Math.min(1, (50.0 - doc['green_space_pct'].value) / 50.0));
                        double acDeficit = Math.max(0, Math.min(1, (100.0 - doc['ac_access_pct'].value) / 30.0));
                        return 1.0 + params.hw * hvi + params.gw * greenDeficit + params.aw * acDeficit;
                    """,
                    "params": {
                        "hw": vulnerability_weight / 100,
                        "gw": vegetation_weight / 100,
                        "aw": ac_weight / 100,
                    },
                },
            }
        },
    )
    rows = []
    for hit in response["hits"]["hits"]:
        row = hit["_source"]
        row["priority_score"] = float(hit["_score"]) - 1.0
        rows.append(row)
    return rows


def allocate_trees(rows: list[dict], total_trees: int = 100) -> list[dict]:
    scores = [max(row["priority_score"], 0) for row in rows]
    total_score = sum(scores) or 1
    raw = [total_trees * score / total_score for score in scores]
    allocations = [int(value) for value in raw]
    for idx in sorted(range(len(raw)), key=lambda i: raw[i] - allocations[i], reverse=True)[: total_trees - sum(allocations)]:
        allocations[idx] += 1
    return [{**row, "trees": trees} for row, trees in zip(rows, allocations)]


class PolicyIntent(BaseModel):
    lead: Literal["heat_equity", "budget_resilience", "emissions"]
    research: Literal["tree_site_feasibility", "bus_total_cost", "building_retrofits"]


def generate_policy_brief(evidence: dict) -> str:
    """Let Mistral set policy emphasis; render evidence deterministically to lock every fact."""
    parsed = mistral_structured(
        PolicyIntent,
        [
            {
                "role": "system",
                "content": (
                    "You are advising a busy NYC mayor who has no climate-policy background. Read the evidence and "
                    "choose the single most important public benefit to lead with and the single study needed before "
                    "spending public money. Favor concrete consequences—safer neighborhoods, lower operating costs, "
                    "or less pollution—over technical climate language. Never assume the reader knows HVI, emissions "
                    "intensity, CO2, Local Law 97, or energy units. Return only the structured choice; do not draft prose, "
                    "invent a budget, set a deadline, or introduce facts."
                ),
            },
            {"role": "user", "content": json.dumps(evidence)},
        ],
    )
    lead = parsed.lead
    research = parsed.research
    lead_text = {
        "heat_equity": "Start where dangerous heat puts the most New Yorkers at risk.",
        "budget_resilience": "Protect the city budget from sudden diesel-price increases.",
        "emissions": "Cut the pollution that traps heat while improving everyday city services.",
    }[lead]
    research_text = {
        "tree_site_feasibility": "fund block-level site surveys, utility checks, tree-species selection, and survival monitoring before committing planting dollars",
        "bus_total_cost": "fund a depot-by-depot total-cost study covering vehicles, chargers, construction, financing, maintenance, batteries, and demand charges",
        "building_retrofits": "fund engineering audits that convert building peer gaps into verified retrofit scopes, costs, and implementation schedules",
    }[research]
    trees = evidence["trees"]
    bus = evidence["buses_modeled_scenario"]
    oil = evidence["fuel_prices_observed"]
    city = evidence.get("city_emissions_context", {})
    buildings = evidence["buildings"]
    top = ", ".join(f"{row['name']} ({row['trees']} trees)" for row in trees["top_neighborhoods"])
    bus_reduction_tons = bus["operational_co2_reduction_thousand_metric_tons"] * 1000
    citywide_share = (
        bus_reduction_tons / city["citywide_2021_metric_tons"] * 100
        if city.get("citywide_2021_metric_tons")
        else None
    )
    scale_sentence = (
        f" That is about **{citywide_share:.1f}% of NYC’s roughly 51 million metric tons of citywide pollution "
        "reported for 2021**."
        if citywide_share is not None
        else ""
    )
    return (
        f"## Bottom line\n**{lead_text}** Do three things together: test a small tree program in the hottest, "
        "least-green neighborhoods; finish the financial homework needed to electrify buses; and help high-polluting "
        "apartment buildings identify practical upgrades.\n\n"
        "## What the evidence says\n"
        f"**Trees:** Start with a planning pool of **{trees['planning_allocation']} trees**. The first neighborhoods are "
        f"{top}. They rise to the top because the ranking emphasizes danger during heat waves "
        f"({trees['weights']['heat_vulnerability']}%), lack of trees and other greenery "
        f"({trees['weights']['vegetation_deficit']}%), and homes without air conditioning "
        f"({trees['weights']['ac_access_deficit']}%).\n\n"
        f"**Buses:** If the miles currently traveled by diesel buses were instead traveled by electric buses, the city’s "
        f"yearly electricity cost would be about **&#36;{abs(bus['annual_energy_cost_change_millions']):,.1f} million "
        f"{'lower' if bus['annual_energy_cost_change_millions'] >= 0 else 'higher'} than its diesel bill** under these "
        f"assumptions. The buses would also produce about **{bus_reduction_tons:,.0f} "
        f"fewer metric tons of heat-trapping pollution each year** from fuel and electricity use.{scale_sentence} This is not the total "
        "project price.\n\n"
        f"**Fuel-price risk:** A common U.S. crude-oil benchmark rose from an average of **&#36;"
        f"{oil['wti_january_2026_average_per_barrel']:.2f} per barrel in January 2026** to **&#36;"
        f"{oil['wti_september_2026_average_per_barrel']:.2f} in September 2026**. That shows why a diesel-dependent fleet "
        "can create budget surprises. It does not prove what caused the price increase.\n\n"
        f"**Buildings:** The tool compares **{buildings['indexed_multifamily_disclosures']:,} apartment-building reports** "
        "to identify owners who may need help cutting energy waste and meeting New York City’s building-pollution law.\n\n"
        "## What to fund now\n"
        f"Release a limited planning budget first and {research_text}. Require agencies to publish the starting numbers, "
        "the result of each pilot, and a go/no-go recommendation before asking for full construction money.\n\n"
        "## What this brief does not promise\n"
        "The tree list identifies neighborhoods, not exact sidewalks. The bus estimate does not include "
        f"{bus['excluded_costs']}. The building comparison does not prove which repair a property needs. These numbers "
        "are a case for targeted research and pilots—not guaranteed savings or a finished budget."
    )
