# Carbon Copy NYC

Carbon Copy finds a multifamily building's greener peers and calculates how much lower its annual emissions would be if it matched the peer median emissions intensity.

The app also includes an NYC bus-electrification scenario using FY2024 federal transit fuel data, MTA electric-bus energy observations, EIA diesel prices, and official emissions factors.

## What the demo proves

- **Elasticsearch:** full-text building lookup, structured filters, numeric ranges, sorting, and peer-group aggregations.
- **Mistral:** converts verified search results and deterministic calculations into a concise, grounded building-performance briefing.
- **Economic action:** screens multifamily records against the 2024–2029 LL97 R-2 limit and explains the potential benefit of a certified compliance and retrofit plan.
- **NYC climate data:** 2024 Local Law 84 building energy and water disclosures from NYC Open Data (`5zyy-y8am`).

The peer group starts with the same property type and report year, floor area within 25%, and construction year within 15 years. For unusual buildings, Carbon Copy transparently widens those bounds until it finds at least three comparable records. The benchmark gap is:

`(target kgCO2e/ft² - peer median kgCO2e/ft²) × target ft² ÷ 1,000`

It is a benchmark scenario, not a retrofit forecast.

The Local Law 97 economic figure is also a screening estimate. It applies the R-2 limit of 6.75 kg CO2e/ft² and the statutory maximum penalty rate of $268 per excess metric ton to the reported LL84 location-based emissions. Actual compliance requires DOB records and certification by a registered design professional.

## Run the polished interface

The React interface keeps the existing Python analysis intact and exposes it
through a small local FastAPI service. Run these in two terminals:

```bash
source .venv/bin/activate
uvicorn api:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The original Streamlit Evidence Lab remains
available at `http://localhost:8501`.

## Run the original Streamlit interface

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python setup_carbon_copy.py
streamlit run app.py
```

Required values in `.env`:

```text
ELASTIC_ENDPOINT=...
ELASTIC_API_KEY=...
MISTRAL_API_KEY=...
MISTRAL_MODEL=mistral-large-4  # optional
```

## Three-minute demo

1. Search for `432 Park Avenue` and select the matching building.
2. Show its emissions intensity, peer median, and calculated benchmark gap.
3. Compare its three greener twins.
4. Generate the Mistral briefing and emphasize that it uses only retrieved evidence.
