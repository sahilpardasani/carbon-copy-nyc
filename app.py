from __future__ import annotations

import streamlit as st

from bus_scenario import (
    DEFAULT_ELECTRIC_KWH_PER_MILE,
    DIESEL_GALLONS,
    NY_ELECTRIC_PRICE_PER_KWH,
    bus_executive_brief,
    calculate_bus_scenario,
    fetch_diesel_prices,
    fetch_wti_prices,
)

from carbon_copy import (
    LL97_R2_LIMIT_KG_CO2E_FT2,
    REPORT_YEAR,
    elastic_client,
    ensure_data,
    evidence_fallback,
    developer_action,
    explain_with_mistral,
    find_peers,
    format_number,
    search_buildings,
)
from heat_priority import (
    allocate_trees,
    ensure_heat_data,
    generate_policy_brief,
    rank_neighborhoods,
)
from executive_briefing import render_executive_briefing
from climate_signals import ensure_climate_signals


st.set_page_config(page_title="Carbon Copy NYC", page_icon="🏙️", layout="wide")

st.markdown(
    """
<style>
  .block-container {max-width: 1180px; padding-top: 2rem;}
  [data-testid="stMetricValue"] {font-size: 2rem;}
  .eyebrow {letter-spacing:.12em; text-transform:uppercase; color:#5b6b63; font-size:.76rem; font-weight:700;}
  .hero {font-size:3.1rem; line-height:1; margin:.25rem 0 .7rem;}
  .sub {color:#52625b; font-size:1.08rem; max-width:760px;}
  .source {color:#68776f; font-size:.82rem;}
</style>
""",
    unsafe_allow_html=True,
)

briefing_tab, evidence_tab = st.tabs(["✨ Mistral Briefing", "🔎 Evidence Lab"])
with briefing_tab:
    render_executive_briefing()

evidence_context = evidence_tab.__enter__()

st.header("NYC Climate Evidence Lab")
st.markdown(
    "**Jump to:** [New flood, green infrastructure & air-quality data](#more-nyc-climate-signals) · "
    "[Electric buses](#what-if-nycs-diesel-bus-miles-went-electric) · "
    "[Tree priorities](#the-next-100-trees) · "
    "[Building benchmark](#find-your-buildings-greener-twin)"
)
st.info(
    "New: 3,422 measured FloodNet events, 13,975 constructed green-infrastructure assets, "
    "2024 neighborhood air-quality measurements, and modeled 2020s-to-2050s flood exposure are now indexed."
)

st.divider()
st.markdown('<div class="eyebrow">NYC TRANSIT SCENARIO</div>', unsafe_allow_html=True)
st.header("What if NYC’s diesel bus miles went electric?")
st.write(
    "This scenario combines FY2024 National Transit Database fuel use with MTA-observed electric-bus energy "
    "consumption and EIA price history. Move the assumptions to see how fuel-price shocks change the case."
)


@st.cache_data(ttl=3600, show_spinner=False)
def diesel_history():
    return fetch_diesel_prices()


@st.cache_data(ttl=3600, show_spinner=False)
def wti_history_2026():
    return fetch_wti_prices()


try:
    prices = diesel_history()
    latest_price = float(prices.iloc[-1]["diesel_price"])
    baseline_2025 = float(prices[prices["date"].dt.year == 2025]["diesel_price"].mean())
except Exception:
    prices = None
    latest_price = 6.199
    baseline_2025 = 3.65

try:
    wti_prices = wti_history_2026()
except Exception:
    wti_prices = None

st.subheader("Real 2026 oil and diesel prices")
st.caption(
    "WTI is a benchmark crude-oil price per barrel. Retail diesel is the price paid per gallon; it also includes "
    "refining, distribution, taxes, and market conditions, so the two series should not be compared dollar-for-dollar."
)

chart_left, chart_right = st.columns(2)
with chart_left:
    st.markdown("**WTI crude oil · Jan–Sep 2026**")
    if wti_prices is not None and not wti_prices.empty:
        st.line_chart(wti_prices.set_index("date")["wti_price"], y_label="Dollars per barrel")
with chart_right:
    st.markdown("**U.S. retail diesel · Jan–Sep 2026**")
    if prices is not None:
        diesel_2026 = prices[
            (prices["date"] >= "2026-01-01") & (prices["date"] <= "2026-09-30")
        ]
        st.line_chart(diesel_2026.set_index("date")["diesel_price"], y_label="Dollars per gallon")

if wti_prices is not None and not wti_prices.empty:
    wti_monthly = (
        wti_prices.assign(month=wti_prices["date"].dt.strftime("%b"))
        .groupby("month", sort=False)["wti_price"]
        .mean()
        .round(2)
    )
    jan_wti = float(wti_monthly.iloc[0])
    sep_wti = float(wti_monthly.iloc[-1])
    peak_row = wti_prices.loc[wti_prices["wti_price"].idxmax()]
    p1, p2, p3 = st.columns(3)
    p1.metric("January WTI average", f"${jan_wti:.2f}/barrel")
    p2.metric(
        "September WTI average",
        f"${sep_wti:.2f}/barrel",
        f"{((sep_wti / jan_wti) - 1) * 100:+.0f}% vs January",
    )
    p3.metric(
        "Weekly peak through September",
        f"${peak_row['wti_price']:.2f}/barrel",
        peak_row["date"].strftime("week of %b %d"),
        delta_color="off",
    )
    with st.expander("See January–September monthly WTI averages"):
        st.dataframe(
            wti_monthly.rename("WTI average ($/barrel)").to_frame(),
            use_container_width=True,
        )

c1, c2, c3 = st.columns(3)
with c1:
    diesel_price = st.slider("Diesel price ($/gallon)", 2.0, 9.0, latest_price, 0.05)
with c2:
    electricity_price = st.slider(
        "Electricity price ($/kWh)", 0.05, 0.50, NY_ELECTRIC_PRICE_PER_KWH, 0.01
    )
with c3:
    electric_efficiency = st.slider(
        "Electric bus energy use (kWh/mile)", 2.0, 6.0, DEFAULT_ELECTRIC_KWH_PER_MILE, 0.1
    )

bus_result = calculate_bus_scenario(diesel_price, electricity_price, electric_efficiency)
b1, b2, b3, b4 = st.columns(4)
b1.metric("FY2024 diesel use", f"{DIESEL_GALLONS / 1_000_000:.1f}M gallons")
b2.metric("Modeled electricity", f"{bus_result.electric_kwh / 1_000_000:.0f}M kWh")
b3.metric(
    "Annual energy-cost change",
    f"${abs(bus_result.energy_cost_change) / 1_000_000:.1f}M {'lower' if bus_result.energy_cost_change >= 0 else 'higher'}",
)
b4.metric(
    "Operational CO₂ change",
    f"{bus_result.operational_co2_change_tons / 1000:.0f}K tons lower",
)

price_shock_cost = (latest_price - baseline_2025) * DIESEL_GALLONS
st.info(
    f"At the latest EIA price (${latest_price:.2f}/gal), the modeled diesel bill is "
    f"${price_shock_cost / 1_000_000:,.1f} million higher than at the 2025 average "
    f"(${baseline_2025:.2f}/gal). This measures price exposure; it does not prove that any specific conflict caused the change."
)

if st.button("Generate plain-English bus brief", use_container_width=True):
    with st.spinner("Mistral is choosing the most decision-relevant takeaway…"):
        try:
            st.markdown(bus_executive_brief(bus_result, latest_price, baseline_2025))
        except Exception:
            direction = "lower" if bus_result.energy_cost_change >= 0 else "higher"
            st.markdown(
                f"Replacing the modeled diesel travel with electric buses would make annual energy spending about "
                f"**${abs(bus_result.energy_cost_change) / 1_000_000:,.1f} million {direction}** and reduce operating "
                f"emissions by about **{bus_result.operational_co2_change_tons / 1000:,.0f} thousand metric tons**, "
                "before accounting for buses, chargers, depot construction, financing, maintenance, and demand charges."
            )

with st.expander("Bus scenario sources and boundaries"):
    st.markdown(
        "- [FTA National Transit Database FY2024 fuel and energy](https://www.transit.dot.gov/ntd/data-product/2024-fuel-and-energy)\n"
        "- [MTA Zero-Emission Bus Transition Plan](https://www.mta.info/document/120411)\n"
        "- [EIA weekly diesel prices](https://www.eia.gov/opendata/browser/petroleum/pri/gnd)\n"
        "- [EIA New York electricity profile](https://www.eia.gov/electricity/state/newyork/)\n"
        "- [EPA mobile-combustion emission factors](https://www.epa.gov/climateleadership/ghg-emission-factors-hub)\n\n"
        "The scenario covers reported diesel bus travel, not CNG service. It models operating energy and direct/grid "
        "carbon only. It excludes vehicle procurement, chargers, depot construction, financing, maintenance, battery "
        "replacement, demand charges, service constraints, and health benefits."
    )

st.divider()
st.markdown('<div class="eyebrow">HEAT-RESILIENCE ALLOCATION</div>', unsafe_allow_html=True)
st.header("The Next 100 Trees")
st.write(
    "Choose what matters most, then Elasticsearch ranks NYC neighborhoods and distributes a limited planning "
    "allocation. This identifies neighborhoods for follow-up—not exact planting sites."
)

try:
    heat_count = ensure_heat_data(es if "es" in locals() else elastic_client())
    heat_es = es if "es" in locals() else elastic_client()
except Exception as exc:
    st.error(f"Heat data setup failed: {exc}")
    heat_count = 0
    heat_es = None

preset = st.radio(
    "Policy priority",
    ["Balanced", "Protect highest-risk neighborhoods", "Close the vegetation gap", "Limited AC access"],
    horizontal=True,
)
presets = {
    "Balanced": (50, 35, 15),
    "Protect highest-risk neighborhoods": (75, 15, 10),
    "Close the vegetation gap": (25, 65, 10),
    "Limited AC access": (30, 15, 55),
}
hw, gw, aw = presets[preset]
st.caption(f"Explicit scoring weights: heat vulnerability **{hw}%** · vegetation deficit **{gw}%** · AC-access deficit **{aw}%**")

if heat_es is not None:
    heat_rows = allocate_trees(rank_neighborhoods(heat_es, hw, gw, aw))
    heat_table = [
        {
            "Neighborhood": row["neighborhood"],
            "HVI (1–5)": row["hvi"],
            "Green space": f"{row['green_space_pct']:.1f}%",
            "Households with AC": f"{row['ac_access_pct']:.1f}%",
            "Surface temperature": f"{row['surface_temp_f']:.1f}°F",
            "Planning allocation": row["trees"],
        }
        for row in heat_rows
    ]
    st.dataframe(heat_table, use_container_width=True, hide_index=True)
    st.caption(
        f"Ranked from {heat_count} NYC neighborhood records. Allocations sum to 100 and change with the selected "
        "policy weights. Field surveys, utilities, sidewalks, ownership, and tree survival determine feasible sites."
    )

    st.subheader("Mistral policy brief for NYC leadership")
    st.write(
        "Mistral combines the verified building, bus, fuel-price, and heat-priority evidence into a funding and research case."
    )
    if st.button("Generate NYC climate-resilience brief", type="primary", use_container_width=True):
        diesel_jan_sep = prices[(prices["date"] >= "2026-01-01") & (prices["date"] <= "2026-09-30")]
        evidence = {
            "audience": "NYC Mayor or City Council member",
            "trees": {
                "planning_allocation": 100,
                "weights": {"heat_vulnerability": hw, "vegetation_deficit": gw, "ac_access_deficit": aw},
                "top_neighborhoods": [
                    {
                        "name": row["neighborhood"],
                        "trees": row["trees"],
                        "hvi": row["hvi"],
                        "green_space_pct": round(row["green_space_pct"], 1),
                    }
                    for row in heat_rows[:5]
                ],
            },
            "buses_modeled_scenario": {
                "fy2024_diesel_gallons": round(DIESEL_GALLONS),
                "annual_energy_cost_change_millions": round(bus_result.energy_cost_change / 1_000_000, 1),
                "operational_co2_reduction_thousand_metric_tons": round(bus_result.operational_co2_change_tons / 1000),
                "excluded_costs": "vehicles, chargers, depots, financing, maintenance, batteries, demand charges",
            },
            "fuel_prices_observed": {
                "wti_january_2026_average_per_barrel": round(jan_wti, 2),
                "wti_september_2026_average_per_barrel": round(sep_wti, 2),
                "diesel_jan_sep_2026_observations": len(diesel_jan_sep),
                "causation_claim": "none",
            },
            "city_emissions_context": {
                "citywide_2021_metric_tons": 51_000_000,
                "nyc_government_fy2024_metric_tons": 2_523_727,
            },
            "buildings": {
                "indexed_multifamily_disclosures": 14281,
                "policy_use": "peer benchmarking and preliminary Local Law 97 screening",
                "not": "an engineering forecast or legal compliance determination",
            },
        }
        with st.spinner("Mistral is drafting from the evidence-locked policy packet…"):
            try:
                st.markdown(generate_policy_brief(evidence))
            except Exception as exc:
                st.error(f"Mistral brief generation failed: {exc}")

with st.expander("Tree-priority data and method"):
    st.markdown(
        "- [NYC Health Heat Vulnerability Explorer](https://a816-dohbesp.nyc.gov/IndicatorPublic/data-features/hvi/)\n"
        "- [NYC Open Data HVI rankings](https://data.cityofnewyork.us/d/4mhf-duep)\n\n"
        "The NYC Health source includes HVI, surface temperature, green space, AC access, and income. HVI runs from "
        "1 (lowest relative vulnerability) to 5 (highest). Elasticsearch normalizes HVI and the two deficits, applies "
        "the displayed weights, and ranks neighborhoods. The 100-tree result is a planning allocation, not a site plan "
        "or a prediction of degrees cooled."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def climate_signals_summary():
    return ensure_climate_signals(elastic_client())


st.subheader("More NYC climate signals")
st.write("Official flood exposure, measured street flooding, green infrastructure, and neighborhood air quality.")
try:
    climate_summary = climate_signals_summary()
    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Measured FloodNet events", f"{climate_summary['flood_event_count']:,}")
    cs2.metric(
        "Constructed green infrastructure",
        f"{climate_summary['green_infrastructure'].get('Constructed', 0):,} assets",
    )
    cs3.metric("Latest air-quality period", climate_summary["air_period"])
    flood_display = [
        {
            "Neighborhood": row["name"],
            "2020s exposed buildings": row["buildings_2020s"],
            "2050s exposed buildings": row["buildings_2050s"],
            "Increase": row["additional_buildings"],
        }
        for row in climate_summary["top_flood_growth"]
    ]
    st.markdown("**Largest modeled growth in buildings exposed to the 100-year flood zone**")
    st.dataframe(flood_display, hide_index=True, width="stretch")
except Exception as exc:
    st.warning(f"Additional climate signals are temporarily unavailable: {exc}")

st.markdown('<div class="eyebrow">NYC BUILDING CLIMATE INTELLIGENCE · 2024</div>', unsafe_allow_html=True)
st.markdown('<div class="hero">Find your building’s greener twin.</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub">Compare a multifamily building with similar NYC properties and measure its gap to the peer median—using public emissions data, Elasticsearch, and Mistral.</div>',
    unsafe_allow_html=True,
)

@st.cache_resource(show_spinner=False)
def get_elastic():
    return elastic_client()


try:
    es = get_elastic()
    with st.spinner("Connecting to Elasticsearch and preparing NYC building data…"):
        building_count = ensure_data(es)
except Exception as exc:
    st.error(f"Setup failed: {exc}")
    st.stop()

st.caption(f"{building_count:,} valid multifamily records indexed from NYC Local Law 84 · Report year {REPORT_YEAR}")

query = st.text_input(
    "Search by building name, street address, ZIP code, or borough",
    value="432 Park Avenue",
    placeholder="Try 432 Park Avenue, CitySpire, 10019…",
)

matches = search_buildings(es, query)
if not matches:
    st.warning("No building matched that search. Try a shorter address or ZIP code.")
    st.stop()

labels = [f"{b['property_name']} — {b['address']}, {b['borough']}" for b in matches]
selection = st.selectbox("Choose a building", labels)
target = matches[labels.index(selection)]

try:
    result = find_peers(es, target)
except RuntimeError as exc:
    st.warning(str(exc))
    st.stop()

st.divider()
st.subheader(target["property_name"])
st.caption(f"{target['address']}, {target['borough']} · Built {target['year_built']} · {target['floor_area_sqft']:,.0f} ft²")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Emissions intensity", f"{target['ghg_intensity']:.2f} kg CO₂e/ft²")
m2.metric("Peer median", f"{result.median_intensity:.2f} kg CO₂e/ft²")
m3.metric(
    "Performance vs median",
    f"{abs(result.percent_vs_median):.0f}% {'above' if result.percent_vs_median >= 0 else 'below'}",
)
m4.metric(
    "Gap to peer median",
    f"{format_number(abs(result.emissions_gap_tons))} t CO₂e/yr",
    delta="opportunity" if result.emissions_gap_tons >= 0 else "already ahead",
    delta_color="inverse" if result.emissions_gap_tons >= 0 else "normal",
)

st.caption(
    f"Compared with {result.peer_count:,} {target['property_type'].lower()} peers from {REPORT_YEAR}, "
    f"using {result.peer_definition.lower()} The benchmark gap is the target’s "
    "floor area multiplied by the difference from peer-median emissions intensity."
)

st.subheader("Greener twins")
if result.greener_twins:
    cols = st.columns(len(result.greener_twins))
    for col, twin in zip(cols, result.greener_twins):
        with col:
            st.markdown(f"**{twin['property_name']}**")
            st.caption(f"{twin['address']}, {twin['borough']}")
            st.metric("GHG intensity", f"{twin['ghg_intensity']:.2f} kg CO₂e/ft²")
            st.write(
                f"Built **{twin['year_built']}** · **{twin['floor_area_sqft']:,.0f} ft²**  \n"
                f"Site EUI **{twin['site_eui']:.1f} kBtu/ft²**"
            )
else:
    st.success("This building already has lower emissions intensity than every matched peer.")

st.subheader("Ask Carbon Copy")
question = st.text_input(
    "Question",
    value="Show me similar NYC buildings that use less energy. How far behind are we?",
    label_visibility="collapsed",
)
if st.button("Generate evidence-based briefing", type="primary", use_container_width=True):
    with st.spinner("Mistral is reading the verified Elastic results…"):
        try:
            st.markdown(explain_with_mistral(result, question))
        except Exception:
            st.warning("Mistral was unavailable or changed a verified figure, so Carbon Copy used its evidence-safe briefing.")
            st.markdown(f"{evidence_fallback(result)}\n\n{developer_action(result)}")

with st.expander("How the Local Law 97 economic screen works"):
    st.markdown(
        f"Carbon Copy compares the reported LL84 location-based emissions intensity with the "
        f"2024–2029 R-2 apartment limit of **{LL97_R2_LIMIT_KG_CO2E_FT2:.2f} kg CO₂e/ft²**, then "
        "multiplies a positive screened overage by the statutory maximum rate of **$268 per metric ton**. "
        "It is a prioritization signal, not a filing or legal determination."
    )

st.divider()
st.markdown(
    '<div class="source">Source: NYC Open Data, Local Law 84 building energy and water disclosures. '
    'Reported data may contain owner-submitted errors. Peer comparisons are descriptive benchmarks, not causal or engineering estimates.</div>',
    unsafe_allow_html=True,
)

evidence_tab.__exit__(None, None, None)
