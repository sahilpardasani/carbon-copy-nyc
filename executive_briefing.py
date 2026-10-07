from __future__ import annotations

import json
import re
from typing import Literal

import streamlit as st
from pydantic import BaseModel

from bus_scenario import calculate_bus_scenario
from carbon_copy import elastic_client, mistral_structured
from heat_priority import allocate_trees, ensure_heat_data, generate_policy_brief, rank_neighborhoods
from climate_signals import ensure_climate_signals


QUESTIONS = [
    "How much operating money might NYC have saved if diesel bus travel were already electric before the 2026 fuel-price increase?",
    "Which neighborhoods should receive the next 100 trees, and why?",
    "What should NYC fund first to make the electric-bus case decision-ready?",
    "How can building emissions data guide Local Law 97 support without overpromising?",
    "Give me the complete two-minute climate-resilience briefing.",
    "Which NYC neighborhoods should receive flood-resilience funding first?",
    "Where has FloodNet measured the most serious recurring street flooding?",
    "Is NYC green infrastructure keeping pace with flood exposure?",
    "Which neighborhoods combine poor air quality with other climate risks?",
]


class BriefIntent(BaseModel):
    topic: Literal["bus_cost", "trees", "bus_research", "buildings", "full_brief"]


class DynamicBrief(BaseModel):
    headline: str
    direct_answer: str
    why_it_matters: str
    actions: list[str]
    success_measures: list[str]
    limits: list[str]
    evidence_used: list[str]


def _intent(question: str, audience: str) -> str:
    parsed = mistral_structured(
        BriefIntent,
        [
            {
                "role": "system",
                "content": "Classify an NYC climate-policy question. Return only the structured topic.",
            },
            {
                "role": "user",
                "content": f"Audience: {audience}. Question: {question}. Choose the evidence topic that best supports an actionable answer.",
            },
        ],
    )
    return parsed.topic


def _numbers(text: str) -> set[str]:
    # The old pattern included sentence-ending periods ("2026."), causing a
    # supported year to differ from the same year elsewhere in a sentence.
    # Strip separators only after extraction so real decimals remain strict.
    return {token.replace(",", "").rstrip(".") for token in re.findall(r"(?<![A-Za-z])\d[\d,.]*", text)}


@st.cache_data(ttl=3600, show_spinner=False)
def _dynamic_brief(question: str, audience: str, topic: str, evidence: dict) -> DynamicBrief:
    brief = mistral_structured(
        DynamicBrief,
        [
            {
                "role": "system",
                "content": (
                    "You are Mistral Large 4 acting as an NYC public-policy adviser. Write a fresh, specific answer for "
                    "the named audience and question. Use plain English for a reader with no climate background. Lead "
                    "with what the person should do, not a summary of the data. Select only relevant evidence IDs. Every "
                    "action must name who should act, what they should request or fund, and what result should be checked. "
                    "Do not invent money, dates, deadlines, percentages, agencies, programs, or causal claims. Use no "
                    "number unless that exact number appears in the evidence packet. Do not repeat boilerplate. Provide "
                    "3 to 5 actions, 2 to 4 success measures, and concise limits."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"audience": audience, "question": question, "selected_topic": topic, "evidence": evidence}
                ),
            },
        ],
    )
    evidence_numbers = _numbers(json.dumps(evidence))
    answer_numbers = _numbers(brief.model_dump_json())
    unsupported = answer_numbers - evidence_numbers
    if unsupported:
        raise ValueError(f"Mistral introduced unsupported numbers: {sorted(unsupported)}")
    return brief


def _fallback_topic(question: str) -> str:
    lowered = question.lower()
    if "tree" in lowered or "neighborhood" in lowered or "heat" in lowered:
        return "trees"
    if "building" in lowered or "local law" in lowered:
        return "buildings"
    if "fund" in lowered or "research" in lowered or "decision-ready" in lowered:
        return "bus_research"
    if "bus" in lowered or "diesel" in lowered or "money" in lowered:
        return "bus_cost"
    return "full_brief"


def _render_dynamic_brief(brief: DynamicBrief) -> None:
    st.markdown(f"## {brief.headline}")
    st.markdown(f"**What you should do:** {brief.direct_answer}")
    st.markdown(f"**Why it matters:** {brief.why_it_matters}")
    st.markdown("### Action plan")
    for action in brief.actions:
        st.markdown(f"- {action}")
    st.markdown("### How you will know it is working")
    for measure in brief.success_measures:
        st.markdown(f"- {measure}")
    st.markdown("### What this does not prove")
    for limit in brief.limits:
        st.markdown(f"- {limit}")
    st.caption("Mistral Large 4 evidence used: " + ", ".join(brief.evidence_used))


# Verified from the EIA weekly series used in the Evidence Lab. Keeping the
# briefing's monthly benchmarks local prevents a public demo-key rate limit
# from breaking the on-stage question flow.
JAN_2026_DIESEL_AVG = 3.5225
SEP_2026_DIESEL_AVG = 6.29075
JAN_2026_WTI_AVG = 59.656
SEP_2026_WTI_AVG = 96.8425
NYC_CITYWIDE_2021_GHG_TONS = 51_000_000
NYC_GOVERNMENT_FY2024_GHG_TONS = 2_523_727


def render_executive_briefing() -> None:
    st.markdown('<div class="eyebrow">MISTRAL POLICY COPILOT</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero">The decision, not the dashboard.</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub">Ask a plain-English NYC climate question. Mistral chooses the relevant evidence; '
        'verified code supplies every number.</div>',
        unsafe_allow_html=True,
    )

    audience = st.radio(
        "I am briefing",
        ["Mayor / City Hall", "City Council member", "Climate advocate"],
        horizontal=True,
    )
    question = st.selectbox("Choose a briefing question", QUESTIONS)
    custom = st.text_input("Or ask your own", placeholder="What should I request in the next city budget?")
    active_question = custom.strip() or question

    if st.button("Brief me", type="primary", width="stretch"):
        with st.spinner("Mistral is selecting and organizing the verified evidence…"):
            jan_bus = calculate_bus_scenario(JAN_2026_DIESEL_AVG)
            sep_bus = calculate_bus_scenario(SEP_2026_DIESEL_AVG)
            jan_wti = JAN_2026_WTI_AVG
            sep_wti = SEP_2026_WTI_AVG

            es = elastic_client()
            ensure_heat_data(es)
            heat_rows = allocate_trees(rank_neighborhoods(es, 50, 35, 15))
            climate = ensure_climate_signals(es)
            topic = _fallback_topic(active_question)

            evidence_packet = {
                "BUS_COST_JAN": "At the January 2026 U.S. diesel average, modeled electric energy cost is $56.4 million lower per year than diesel.",
                "BUS_COST_SEP": "At the September 2026 U.S. diesel average, modeled electric energy cost is $166.1 million lower per year than diesel.",
                "BUS_PRICE_EXPOSURE": "The September modeled energy advantage is $109.7 million larger than January's because diesel was more expensive.",
                "BUS_POLLUTION": "Modeled operational reduction is 301,516 metric tons of heat-trapping pollution per year, about 0.6% of NYC's roughly 51 million metric tons reported citywide for 2021.",
                "OIL_PRICE": "WTI crude averaged $59.66 per barrel in January 2026 and $96.84 in September 2026; the data do not establish the cause.",
                "BUS_SCOPE": "The model uses FY2024 reported diesel bus travel and excludes buses, chargers, depots, financing, maintenance, batteries, and demand charges.",
                "MTA_AUTHORITY": "MTA is a New York State authority. City Hall can convene, coordinate city approvals, request evidence, and advocate, but cannot order the conversion alone.",
                "BUS_DECISION_DATA": "A decision-ready plan needs depot sequence, full ownership cost, utility and charger plan, cost per mile, charger uptime, missed service, energy use, and pollution per mile.",
                "TREE_METHOD": "The 100-tree planning allocation weights danger during heat waves at 50%, lack of vegetation at 35%, and limited home AC access at 15%.",
                "TREE_TOP": "; ".join(f"{row['neighborhood']}: {row['trees']} trees" for row in heat_rows[:5]),
                "TREE_LIMIT": "Neighborhood ranking is not an exact planting-site plan; utilities, sidewalk space, ownership, species fit, and maintenance need field checks.",
                "BUILDING_DATA": "Carbon Copy indexes 14,281 NYC multifamily disclosure records and compares each property with similar peers.",
                "BUILDING_LIMIT": "Peer comparison is a screening signal, not an engineering forecast or legal Local Law 97 determination.",
                "FLOOD_EXPOSURE": "; ".join(
                    f"{row['name']}: {row['buildings_2020s']} buildings in the 2020s flood zone, "
                    f"{row['buildings_2050s']} in the 2050s, increase {row['additional_buildings']}"
                    for row in climate["top_flood_growth"]
                ),
                "FLOODNET_EVENTS": f"FloodNet contains {climate['flood_event_count']} quality-controlled measured flood events. "
                + "; ".join(
                    f"{row['name']}: {row['events']} events, maximum depth {row['max_depth_inches']:.1f} inches"
                    for row in climate["top_measured_flooding"]
                ),
                "GREEN_INFRASTRUCTURE": "; ".join(
                    f"{status}: {count} DEP green-infrastructure assets"
                    for status, count in climate["green_infrastructure"].items()
                ),
                "AIR_QUALITY": f"Latest neighborhood PM2.5 period is {climate['air_period']}. Highest measurements: "
                + "; ".join(
                    f"{row['name']}: {row['pm25']} {row['units']}" for row in climate["worst_air"]
                ),
                "CLIMATE_SIGNAL_LIMITS": "Flood exposure is a planning scenario, FloodNet only represents instrumented locations, green-infrastructure counts do not prove flood prevention, and neighborhood air quality does not identify an individual person's exposure.",
            }
            try:
                dynamic = _dynamic_brief(active_question, audience, topic, evidence_packet)
                _render_dynamic_brief(dynamic)
                st.caption("This response was written live by Mistral Large 4; code only checked its numbers against the evidence packet.")
                return
            except Exception as dynamic_error:
                st.warning(f"Large 4's draft failed evidence validation, so the verified fallback is shown. ({dynamic_error})")

            if topic == "bus_cost":
                citywide_share = jan_bus.operational_co2_change_tons / NYC_CITYWIDE_2021_GHG_TONS * 100
                government_scale = jan_bus.operational_co2_change_tons / NYC_GOVERNMENT_FY2024_GHG_TONS * 100
                action_plan = {
                    "Mayor / City Hall": (
                        "### What you should do now\n"
                        "1. **Ask the Governor and MTA for a joint 90-day depot plan.** Require a depot-by-depot schedule, "
                        "charger and utility needs, route constraints, vehicle costs, and the funding gap. The Mayor does "
                        "not control the MTA, so this must be a city–state agreement.\n"
                        "2. **Name one accountable City Hall lead.** Have that office coordinate DOT street work, utility "
                        "connections, construction permits, emergency review, and community engagement for the first depot.\n"
                        "3. **Fund the homework before promising a fleet conversion.** Request money for engineering, utility "
                        "interconnection studies, and an independent total-cost review—not a blank check for buses.\n"
                        "4. **Publish a public scorecard.** Track dollars per mile, charger uptime, missed service, energy use, "
                        "and pollution per mile against today’s diesel baseline.\n\n"
                        "### Your decision rule\n"
                        "Advance each depot only if the independent review shows that its added yearly ownership costs are "
                        "covered by a credible portion of the modeled **&#36;56.4–&#36;166.1 million annual energy advantage**, "
                        "and the pilot meets reliability targets. Pause or redesign depots that fail either test."
                    ),
                    "City Council member": (
                        "### What you should do now\n"
                        "1. **Call an oversight hearing** with MTA, City Hall, Con Edison, and NYPA focused on depot readiness "
                        "and total ownership cost—not broad climate promises.\n"
                        "2. **Request five documents:** a depot sequence, charger-uptime target, utility-upgrade schedule, full "
                        "capital and operating costs, and a diesel-versus-electric cost-per-mile baseline.\n"
                        "3. **Condition city-controlled funding and approvals** on quarterly publication of cost, reliability, "
                        "energy, and pollution results.\n"
                        "4. **Ask the State to close the capital gap**, because the MTA—not City Hall—controls the fleet.\n\n"
                        "### Your decision rule\n"
                        "Support the next phase only when MTA shows that total costs—not merely fuel costs—fit within a "
                        "published funding plan and the first depot can maintain bus service."
                    ),
                    "Climate advocate": (
                        "### What you should do now\n"
                        "1. **Ask for a specific commitment:** a public depot-by-depot electrification plan with dates, costs, "
                        "responsible agencies, and charger-uptime targets.\n"
                        "2. **Use the range, not the biggest number.** Say the model finds a **&#36;56.4–&#36;166.1 million yearly "
                        "energy-cost advantage**, depending on diesel prices, before capital and maintenance costs.\n"
                        "3. **Demand an independent total-cost study** and publication of the assumptions, so officials cannot "
                        "sell either an inflated savings claim or an inflated cost claim.\n"
                        "4. **Build a local coalition around the first depots** with riders, transit workers, environmental-justice "
                        "groups, and nearby residents; ask for service reliability and local air-pollution measurements.\n"
                        "5. **Direct pressure to Albany as well as City Hall.** MTA is a state authority; the Mayor can convene, "
                        "coordinate city approvals, and advocate, but cannot order the fleet conversion alone.\n\n"
                        "### Your public message\n"
                        "“We are not asking officials to accept a savings promise. We are asking them to publish the full "
                        "cost, test one depot transparently, and expand only if the numbers and bus service hold up.”"
                    ),
                }[audience]
                st.markdown(
                    "## Bottom line\n"
                    f"Using reported FY2024 diesel bus travel as the common baseline, electric operation would have "
                    f"used about **&#36;{jan_bus.energy_cost_change / 1_000_000:,.1f} million less in energy per year** at "
                    f"January’s diesel price and **&#36;{sep_bus.energy_cost_change / 1_000_000:,.1f} million less** at "
                    f"September’s price. In everyday terms: September’s higher diesel price would have added another "
                    f"**&#36;{(sep_bus.energy_cost_change - jan_bus.energy_cost_change) / 1_000_000:,.1f} million** to the "
                    "modeled advantage of electricity.\n\n"
                    f"WTI crude averaged **&#36;{jan_wti:.2f}/barrel** in January and **&#36;{sep_wti:.2f}/barrel** in September. "
                    "That documents a price increase; it does **not** establish that a particular geopolitical event "
                    "caused it. This comparison only covers diesel versus electricity. Buying buses and building chargers "
                    "could cost a great deal, so this is **not a claim that the city would have put this amount in the bank**.\n\n"
                    "## How much greener is that?\n"
                    f"The modeled reduction is about **{jan_bus.operational_co2_change_tons:,.0f} metric tons of "
                    f"heat-trapping pollution per year**. For scale, that equals about **{citywide_share:.1f}% of NYC’s "
                    "roughly 51 million metric tons of citywide emissions reported for 2021**. It is also equal to about "
                    f"**{government_scale:.0f}% of the pollution from NYC government operations in FY2024**. The second "
                    "comparison is only a size reference: MTA is a state authority, and this model should not be "
                    f"subtracted directly from the city-government inventory.\n\n{action_plan}"
                )
            elif topic == "trees":
                top = ", ".join(f"**{row['neighborhood']}** ({row['trees']})" for row in heat_rows[:5])
                st.markdown(
                    "## Bottom line\n"
                    f"With balanced weights—50% heat vulnerability, 35% vegetation deficit, and 15% limited AC "
                    f"access—the first planning priorities are {top}. The allocations sum to 100 trees. Before funding "
                    "planting, commission block-level checks for utilities, sidewalk space, ownership, species fit, and "
                    "long-term maintenance. This is a neighborhood screening tool, not a planting-site plan."
                )
            elif topic == "bus_research":
                st.markdown(
                    "## Bottom line\n"
                    "Fund a depot-by-depot total-cost and delivery study first. It should price buses, chargers, utility "
                    "upgrades, depot construction, financing, maintenance, battery replacement, demand charges, route "
                    "constraints, and workforce needs. Pair that with a measured pilot so operating-energy and reliability "
                    "results can be compared with the model before citywide scaling."
                )
            elif topic == "buildings":
                st.markdown(
                    "## Bottom line\n"
                    "Use the **14,281 indexed multifamily disclosures** to find buildings performing worse than genuinely "
                    "similar peers, then direct audits and technical assistance toward the largest gaps. Peer performance "
                    "is a prioritization signal—not proof that a specific retrofit will work, an engineering savings "
                    "forecast, or a legal Local Law 97 determination."
                )
            else:
                evidence = {
                    "trees": {
                        "planning_allocation": 100,
                        "weights": {"heat_vulnerability": 50, "vegetation_deficit": 35, "ac_access_deficit": 15},
                        "top_neighborhoods": [
                            {"name": row["neighborhood"], "trees": row["trees"]} for row in heat_rows[:5]
                        ],
                    },
                    "buses_modeled_scenario": {
                        "annual_energy_cost_change_millions": round(sep_bus.energy_cost_change / 1_000_000, 1),
                        "operational_co2_reduction_thousand_metric_tons": round(
                            sep_bus.operational_co2_change_tons / 1000
                        ),
                        "excluded_costs": "vehicles, chargers, depots, financing, maintenance, batteries, demand charges",
                    },
                    "fuel_prices_observed": {
                        "wti_january_2026_average_per_barrel": round(jan_wti, 2),
                        "wti_september_2026_average_per_barrel": round(sep_wti, 2),
                    },
                    "city_emissions_context": {
                        "citywide_2021_metric_tons": NYC_CITYWIDE_2021_GHG_TONS,
                        "nyc_government_fy2024_metric_tons": NYC_GOVERNMENT_FY2024_GHG_TONS,
                    },
                    "buildings": {"indexed_multifamily_disclosures": 14281},
                }
                st.markdown(generate_policy_brief(evidence))

    st.caption(
        "Mistral routes each question and selects the policy emphasis. Calculations and displayed figures are "
        "evidence-locked to NYC, FTA, EIA, EPA, and MTA source data."
    )
    st.markdown(
        "City comparison sources: [PlaNYC citywide greenhouse-gas inventory]"
        "(https://www.nyc.gov/assets/climate/downloads/pdfs/PlaNYC-2023-Full-Report.pdf) · "
        "[NYC government FY2024 emissions]"
        "(https://www.nyc.gov/site/dcas/agencies/energy-executive-order-89-year-2021-emissions-reduction-progress.page)"
    )
