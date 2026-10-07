from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
import requests
from pydantic import BaseModel

from carbon_copy import mistral_structured


# FY2024 National Transit Database totals for MTA New York City Transit
# (bus, bus rapid transit, commuter bus) plus MTA Bus Company.
DIESEL_GALLONS = 39_623_877.0
DIESEL_MILES = 131_379_459.0
DEFAULT_ELECTRIC_KWH_PER_MILE = 3.22  # MTA observed standard electric buses
NY_ELECTRIC_PRICE_PER_KWH = 0.1966  # EIA 2024 all-sector NY average
NY_GRID_KG_CO2_PER_KWH = 537 * 0.453592 / 1000  # EIA 2024: 537 lb/MWh
DIESEL_KG_CO2_PER_GALLON = 10.21  # EPA mobile combustion factor

EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
EIA_SERIES = "EMD_EPD2D_PTE_NUS_DPG"
EIA_SPOT_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
EIA_WTI_SERIES = "RWTC"


@dataclass(frozen=True)
class BusScenario:
    diesel_price: float
    electricity_price: float
    kwh_per_mile: float
    diesel_cost: float
    electric_kwh: float
    electric_cost: float
    energy_cost_change: float
    diesel_co2_tons: float
    electric_co2_tons: float
    operational_co2_change_tons: float


class BusIntent(BaseModel):
    priority: Literal["cost_volatility", "emissions", "implementation"]


def fetch_diesel_prices(start: str = "2024-01-01") -> pd.DataFrame:
    response = requests.get(
        EIA_URL,
        params={
            "api_key": "DEMO_KEY",
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": EIA_SERIES,
            "start": start,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": 0,
            "length": 5000,
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()["response"]["data"]
    frame = pd.DataFrame(
        {"date": pd.to_datetime(row["period"]), "diesel_price": float(row["value"])}
        for row in rows
    )
    return frame.sort_values("date").reset_index(drop=True)


def fetch_wti_prices(start: str = "2026-01-01", end: str = "2026-09-30") -> pd.DataFrame:
    """Fetch official weekly Cushing WTI spot prices from the EIA."""
    response = requests.get(
        EIA_SPOT_URL,
        params={
            "api_key": "DEMO_KEY",
            "frequency": "weekly",
            "data[0]": "value",
            "facets[series][]": EIA_WTI_SERIES,
            "start": start,
            "end": end,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": 0,
            "length": 5000,
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()["response"]["data"]
    frame = pd.DataFrame(
        {"date": pd.to_datetime(row["period"]), "wti_price": float(row["value"])}
        for row in rows
    )
    return frame.sort_values("date").reset_index(drop=True)


def calculate_bus_scenario(
    diesel_price: float,
    electricity_price: float = NY_ELECTRIC_PRICE_PER_KWH,
    kwh_per_mile: float = DEFAULT_ELECTRIC_KWH_PER_MILE,
) -> BusScenario:
    diesel_cost = DIESEL_GALLONS * diesel_price
    electric_kwh = DIESEL_MILES * kwh_per_mile
    electric_cost = electric_kwh * electricity_price
    diesel_co2 = DIESEL_GALLONS * DIESEL_KG_CO2_PER_GALLON / 1000
    electric_co2 = electric_kwh * NY_GRID_KG_CO2_PER_KWH / 1000
    return BusScenario(
        diesel_price=diesel_price,
        electricity_price=electricity_price,
        kwh_per_mile=kwh_per_mile,
        diesel_cost=diesel_cost,
        electric_kwh=electric_kwh,
        electric_cost=electric_cost,
        energy_cost_change=diesel_cost - electric_cost,
        diesel_co2_tons=diesel_co2,
        electric_co2_tons=electric_co2,
        operational_co2_change_tons=diesel_co2 - electric_co2,
    )


def bus_executive_brief(scenario: BusScenario, latest_price: float, baseline_price: float) -> str:
    evidence = {
        "diesel_gallons_fy2024": round(DIESEL_GALLONS),
        "diesel_bus_miles_fy2024": round(DIESEL_MILES),
        "latest_eia_diesel_price_per_gallon": round(latest_price, 3),
        "baseline_diesel_price_per_gallon": round(baseline_price, 3),
        "modeled_electricity_kwh": round(scenario.electric_kwh),
        "modeled_energy_cost_change_usd": round(scenario.energy_cost_change),
        "modeled_operational_co2_change_metric_tons": round(scenario.operational_co2_change_tons),
    }
    parsed = mistral_structured(
        BusIntent,
        [
            {
                "role": "system",
                "content": "You choose the most decision-relevant focus for an executive climate briefing.",
            },
            {
                "role": "user",
                "content": (
                    "For a novice executive asking what happens if NYC MTA diesel bus miles become electric, "
                    f"choose whether to emphasize cost volatility, emissions, or implementation. Evidence: {evidence}. "
                    "Return only the structured choice."
                ),
            },
        ],
    )
    priority = parsed.priority
    leads = {
        "cost_volatility": "Mistral’s decision focus: electrification can reduce exposure to diesel-price shocks.",
        "emissions": "Mistral’s decision focus: electrification can substantially reduce operating emissions.",
        "implementation": "Mistral’s decision focus: the opportunity is large, but depot and charging execution determines success.",
    }
    direction = "lower" if scenario.energy_cost_change >= 0 else "higher"
    return (
        f"**{leads[priority]}**\n\n"
        f"If FY2024 diesel bus travel were powered by batteries under these assumptions, annual energy spending "
        f"would be about **${abs(scenario.energy_cost_change) / 1_000_000:,.1f} million {direction}**, before bus purchases, "
        f"chargers, depot upgrades, financing, maintenance, and demand charges. Operational carbon emissions would be "
        f"about **{scenario.operational_co2_change_tons / 1000:,.0f} thousand metric tons lower** using the 2024 New York grid average.\n\n"
        "**Executive action:** phase electrification depot by depot, lock in power and charging plans, and prioritize the "
        "routes with the highest diesel use and pollution exposure. Treat avoided diesel spending as operating-budget "
        "headroom, not as guaranteed project profit."
    )
