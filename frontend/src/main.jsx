import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowDown, ArrowRight, ArrowUp, BarChart3, Building2, Bus, Check, ChevronRight, CloudRain, Copy, DollarSign, ExternalLink, Fuel, Gauge, Leaf, LoaderCircle, MapPin, MessageSquareText, Search, ShieldCheck, SlidersHorizontal, Sparkles, Trees, TrendingUp, Wind, Zap } from 'lucide-react'
import './styles.css'
import './scenario.css'
import './explorers.css'

const questions = [
  ['Bus budgets', 'What should the Mayor do next to make electric buses financially decision-ready?', Bus],
  ['Flood resilience', 'Which NYC neighborhoods should receive flood-resilience funding first?', CloudRain],
  ['Heat & trees', 'Where should NYC prioritize the next 100 trees, and what must happen before planting?', Trees],
  ['Clean air', 'Which neighborhoods combine poor air quality with other climate risks?', Wind],
  ['Buildings', 'How should NYC help apartment buildings cut pollution without overpromising savings?', Building2],
]

const audiences = ['Mayor / City Hall', 'City Council member', 'Climate advocate']

function number(value) { return new Intl.NumberFormat('en-US').format(value || 0) }

function App() {
  const [view, setView] = useState('brief')
  const [audience, setAudience] = useState(audiences[0])
  const [question, setQuestion] = useState(questions[0][1])
  const [overview, setOverview] = useState(null)
  const [brief, setBrief] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => { fetch('/api/overview').then(r => r.ok ? r.json() : Promise.reject(r)).then(setOverview).catch(() => setError('The evidence service is starting. Refresh in a moment.')) }, [])

  async function generate() {
    setLoading(true); setError(''); setBrief(null)
    try {
      const response = await fetch('/api/brief', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ audience, question }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Unable to generate briefing.')
      setBrief(body)
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  function copyBrief() {
    if (!brief) return
    const text = `${brief.headline}\n\n${brief.direct_answer}\n\n${brief.why_it_matters}\n\nAction plan\n${brief.actions.map(x=>`• ${x}`).join('\n')}`
    navigator.clipboard.writeText(text); setCopied(true); setTimeout(()=>setCopied(false), 1800)
  }

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#" aria-label="Carbon Copy NYC home"><span className="brand-mark"><Leaf size={20}/></span><span>Carbon Copy <b>NYC</b></span></a>
      <nav aria-label="Primary navigation">
        <button className={view==='brief'?'nav-active':''} onClick={()=>setView('brief')}>Ask Mistral</button>
        <button className={view==='evidence'?'nav-active':''} onClick={()=>setView('evidence')}>Evidence</button>
      </nav>
      <div className="model-chip"><span></span>Mistral Large 4</div>
    </header>

    <main id="main">
      {view === 'brief' ? <>
        <section className="hero-grid">
          <div className="hero-copy">
            <div className="eyebrow"><Sparkles size={15}/> NYC climate policy copilot</div>
            <h1>Turn city data into<br/><em>decisions that move.</em></h1>
            <p>Ask a plain-English question. Get an actionable plan grounded in verified New York City evidence—not generic climate advice.</p>
            <div className="trust-row"><span><ShieldCheck/> Evidence-locked numbers</span><span><BarChart3/> 5 official data systems</span></div>
          </div>
          <div className="signal-card" aria-label="Live evidence summary">
            <div className="signal-top"><span>LIVE EVIDENCE</span><span className="live-dot">Connected</span></div>
            <div className="signal-map"><div className="orb orb-1"></div><div className="orb orb-2"></div><div className="orb orb-3"></div><span className="map-label"><MapPin size={15}/> New York City</span></div>
            <div className="signal-stats">
              <div><b>{number(overview?.metrics?.buildings_indexed)}</b><span>buildings</span></div>
              <div><b>{number(overview?.metrics?.floodnet_events)}</b><span>flood events</span></div>
              <div><b>{number(overview?.metrics?.green_infrastructure)}</b><span>green assets</span></div>
            </div>
          </div>
        </section>

        <section className="workspace">
          <div className="composer-card">
            <div className="section-label">1 · Who are you briefing?</div>
            <div className="segmented" role="group" aria-label="Briefing audience">
              {audiences.map(a=><button key={a} className={audience===a?'selected':''} onClick={()=>setAudience(a)}>{audience===a&&<Check size={15}/>} {a}</button>)}
            </div>
            <label htmlFor="policy-question" className="section-label question-label">2 · What decision are you trying to make?</label>
            <textarea id="policy-question" value={question} onChange={e=>setQuestion(e.target.value)} rows="4" />
            <div className="composer-footer"><span>Mistral uses only the evidence shown in this app.</span><button className="primary" onClick={generate} disabled={loading||!question.trim()}>{loading?<><LoaderCircle className="spin"/>Analyzing evidence…</>:<>Generate action brief <ArrowRight size={18}/></>}</button></div>
          </div>

          <div className="prompts-panel">
            <div className="section-label">Try a decision</div>
            {questions.map(([label,q,Icon])=><button key={label} className="prompt-card" onClick={()=>setQuestion(q)}><span className="prompt-icon"><Icon size={18}/></span><span><b>{label}</b><small>{q}</small></span><ChevronRight size={17}/></button>)}
          </div>
        </section>

        {error && <div className="error-card" role="alert">{error}</div>}
        {brief && <section className="brief-result" aria-live="polite">
          <div className="brief-header"><div><div className="eyebrow"><MessageSquareText size={15}/> Mistral recommendation</div><h2>{brief.headline}</h2></div><button className="icon-button" onClick={copyBrief} aria-label="Copy briefing">{copied?<Check/>:<Copy/>}</button></div>
          <div className="decision-callout"><span>WHAT YOU SHOULD DO</span><p>{brief.direct_answer}</p></div>
          <p className="why"><b>Why it matters</b>{brief.why_it_matters}</p>
          <div className="brief-columns">
            <div><h3>Action plan</h3>{brief.actions.map((x,i)=><div className="action" key={x}><span>{i+1}</span><p>{x}</p></div>)}</div>
            <div><h3>Measure success</h3>{brief.success_measures.map(x=><div className="checkline" key={x}><Check size={16}/><p>{x}</p></div>)}<div className="limits"><h3>What this does not prove</h3>{brief.limits.map(x=><p key={x}>{x}</p>)}</div></div>
          </div>
          <div className="evidence-strip"><ShieldCheck size={17}/><span><b>Evidence used</b> {brief.evidence_used.join(' · ')}</span></div>
        </section>}
      </> : <Evidence overview={overview}/>} 
    </main>
    <footer><span>Carbon Copy NYC · Elasticsearch + Mistral Large 4</span><a href="http://localhost:8501" target="_blank">Open technical Evidence Lab <ExternalLink size={14}/></a></footer>
  </div>
}

function Evidence({overview}) {
  const metrics = overview?.metrics || {}
  return <section className="evidence-page">
    <div className="eyebrow"><BarChart3 size={15}/> Verified NYC evidence</div>
    <h1>The numbers behind the recommendation.</h1>
    <p className="lede">Observed records, modeled scenarios, and planning assumptions stay visibly separate.</p>
    <div className="metric-grid">
      <Metric icon={Building2} value={number(metrics.buildings_indexed)} label="Multifamily disclosures" note="Observed · NYC LL84" />
      <Metric icon={CloudRain} value={number(metrics.floodnet_events)} label="Measured flood events" note="Observed · FloodNet" />
      <Metric icon={Leaf} value={number(metrics.green_infrastructure)} label="Constructed green assets" note="Observed · NYC DEP" />
      <Metric icon={Bus} value={number(metrics.bus_pollution_reduction)} label="Metric tons avoided / year" note="Modeled bus scenario" />
    </div>
    <div className="evidence-grid">
      <BusScenarioExplorer data={overview?.bus_scenario}/>
      <TreePriorityExplorer initial={overview?.tree_priorities}/>
      <BuildingTwinSearch/>
      <article className="data-card wide"><header><div><span>FUTURE EXPOSURE</span><h2>Buildings entering the flood zone</h2></div><CloudRain/></header><div className="rank-list">{overview?.flood_growth?.map((x,i)=><div key={x.name}><span className="rank">0{i+1}</span><span className="place">{x.name}</span><span className="bar"><i style={{width:`${Math.max(14,x.additional_buildings/32)}%`}}></i></span><b>+{number(x.additional_buildings)}</b></div>)}</div><p className="card-note">Modeled change from the 2020s to 2050s anticipated 100-year flood zone.</p></article>
      <article className="data-card"><header><div><span>AIR QUALITY · {overview?.air_period}</span><h2>Highest PM2.5 readings</h2></div><Wind/></header>{overview?.air_quality?.map(x=><div className="compact-row" key={x.name}><span>{x.name}</span><b>{x.pm25.toFixed(1)}</b></div>)}</article>
    </div>
  </section>
}

function TreePriorityExplorer({initial=[]}) {
  const [weights, setWeights] = useState({vulnerability:50, vegetation:35, ac_access:15})
  const [rows, setRows] = useState(initial)
  const [loading, setLoading] = useState(false)
  const [instruction, setInstruction] = useState('Prioritize neighborhoods with little greenery and poor access to air conditioning. Show what changes from our current tree plan.')
  const [interpreting, setInterpreting] = useState(false)
  const [mistralResult, setMistralResult] = useState(null)
  const [treeError, setTreeError] = useState('')
  useEffect(() => { if (initial?.length && !rows?.length) setRows(initial) }, [initial])
  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const params = new URLSearchParams(weights)
        const response = await fetch(`/api/trees?${params}`)
        if (response.ok) setRows((await response.json()).neighborhoods)
      } finally { setLoading(false) }
    }, 180)
    return () => clearTimeout(timer)
  }, [weights])
  const visibleRows = mistralResult?.neighborhoods || rows
  const maxTrees = Math.max(...visibleRows.map(x=>x.trees), 1)
  const controls = [
    ['vulnerability','Heat danger','How vulnerable residents are during extreme heat'],
    ['vegetation','Low vegetation','How little green space the neighborhood has'],
    ['ac_access','Limited A/C','How many homes lack air conditioning'],
  ]
  async function interpretPriorities() {
    setInterpreting(true); setTreeError('')
    try {
      const response = await fetch('/api/trees/interpret', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({instruction,current_weights:weights})})
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Mistral could not interpret this request.')
      setWeights(body.weights); setRows(body.neighborhoods); setMistralResult(body)
    } catch (e) { setTreeError(e.message) } finally { setInterpreting(false) }
  }
  return <article className="data-card wide tree-explorer">
    <header><div><span>THE NEXT 100 TREES</span><h2>Change the priorities. Watch the map shift.</h2><p>Elasticsearch reranks NYC neighborhoods every time you move a policy weight.</p></div><SlidersHorizontal/></header>
    <div className="natural-control">
      <div className="natural-label"><Sparkles size={16}/><span><b>Tell Mistral what you care about</b><small>It will set explicit weights, rerun Elasticsearch, and compare the rankings.</small></span></div>
      <div className="natural-input"><input value={instruction} onChange={e=>setInstruction(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')interpretPriorities()}} aria-label="Describe tree planning priorities"/><button onClick={interpretPriorities} disabled={interpreting||!instruction.trim()}>{interpreting?<LoaderCircle className="spin"/>:<Sparkles/>}{interpreting?'Translating…':'Apply with Mistral'}</button></div>
      {treeError&&<p className="inline-error">{treeError}</p>}
      {mistralResult&&<div className="mistral-interpretation"><Sparkles size={15}/><span><b>Mistral interpreted your request:</b> {mistralResult.interpretation}</span></div>}
    </div>
    <div className="tree-layout">
      <div className="tree-controls">
        {controls.map(([key,label,help])=><label className="weight-control" key={key}><div><span><b>{label}</b><small>{help}</small></span><output>{weights[key]}%</output></div><input type="range" min="0" max="100" value={weights[key]} onChange={e=>{setMistralResult(null);setWeights({...weights,[key]:Number(e.target.value)})}} style={{'--range-progress':`${weights[key]}%`}}/></label>)}
        <div className="weight-total"><span>Relative emphasis</span><b>{Object.values(weights).reduce((a,b)=>a+b,0)} points</b></div>
      </div>
      <div className={`tree-results ${loading?'is-loading':''}`}>
        <div className="tree-result-head"><span>{mistralResult?'Ranking change':'Highest-priority neighborhoods'}</span><span>{loading?'Reranking…':'100 trees allocated'}</span></div>
        {visibleRows.slice(0,7).map((x,i)=><div className="tree-rank" key={x.nta_code}><span className="tree-position">{String(i+1).padStart(2,'0')}</span><div><b>{x.neighborhood}</b><small>HVI {x.hvi}/5 · {x.green_space_pct.toFixed(0)}% green · {x.ac_access_pct.toFixed(0)}% A/C</small></div><span className="tree-allocation"><i style={{width:`${x.trees/maxTrees*100}%`}}></i></span>{mistralResult?<RankChange row={x}/>:<strong>{x.trees}</strong>}</div>)}
      </div>
    </div>
    <p className="explorer-note">This identifies neighborhoods for planning—not exact planting sites. Utilities, sidewalk space, ownership, species fit and maintenance still require field checks.</p>
  </article>
}

function RankChange({row}) {
  if (row.is_new) return <strong className="rank-new">NEW</strong>
  if (row.rank_change > 0) return <strong className="rank-up"><ArrowUp/> {row.rank_change}</strong>
  if (row.rank_change < 0) return <strong className="rank-down"><ArrowDown/> {Math.abs(row.rank_change)}</strong>
  return <strong className="rank-same">—</strong>
}

function BuildingTwinSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    if (selected || query.trim().length < 2) { setResults([]); return }
    const timer = setTimeout(async () => {
      const response = await fetch(`/api/buildings/search?q=${encodeURIComponent(query)}`)
      if (response.ok) { setResults((await response.json()).results); setOpen(true) }
    }, 220)
    return () => clearTimeout(timer)
  }, [query, selected])
  async function choose(building) {
    setSelected(true); setQuery(`${building.property_name} · ${building.address}`); setOpen(false); setResults([]); setLoading(true); setAnalysis(null)
    try {
      const response = await fetch(`/api/buildings/${encodeURIComponent(building.property_id)}/peers`)
      if (response.ok) setAnalysis(await response.json())
    } finally { setLoading(false) }
  }
  return <article className="data-card wide twin-explorer">
    <div className="twin-intro"><div><span>CARBON COPY · BUILDING SEARCH</span><h2>Find your building’s greener twin.</h2><p>Search an address, building name, or ZIP code. We’ll compare it with similar NYC multifamily buildings.</p></div><Building2/></div>
    <div className="building-search-wrap">
      <Search size={22}/><input value={query} onChange={e=>{setSelected(false);setQuery(e.target.value);setAnalysis(null)}} onFocus={()=>results.length&&setOpen(true)} placeholder="Try 432 Park Avenue or 10001" aria-label="Search NYC buildings"/><span>{loading?<LoaderCircle className="spin"/>:'14,281 buildings'}</span>
      {open&&results.length>0&&<div className="search-suggestions">{results.map(x=><button key={x.property_id} onClick={()=>choose(x)}><span className="suggestion-icon"><Building2/></span><span><b>{x.property_name}</b><small>{x.address} · {x.borough} {x.postal_code}</small></span><span className="suggestion-meta">{number(Math.round(x.floor_area_sqft))} ft²</span></button>)}</div>}
    </div>
    {!analysis&&!loading&&<div className="search-prompts"><span>Recommended:</span>{['432 Park Avenue','Mercedes House','101 Lincoln Ave'].map(x=><button key={x} onClick={()=>{setSelected(false);setQuery(x)}}>{x}</button>)}</div>}
    {loading&&<div className="twin-loading"><LoaderCircle className="spin"/><span>Finding comparable buildings in Elasticsearch…</span></div>}
    {analysis&&<BuildingComparison data={analysis}/>} 
  </article>
}

function BuildingComparison({data}) {
  const t=data.target, above=data.percent_vs_median>=0
  return <div className="building-comparison">
    <div className="building-score"><div><span>SELECTED BUILDING</span><h3>{t.property_name}</h3><p>{t.address} · {t.borough}</p></div><div className={above?'score-bad':'score-good'}><strong>{Math.abs(data.percent_vs_median).toFixed(0)}%</strong><span>{above?'above':'below'} peer median</span></div></div>
    <div className="comparison-metrics"><div><span>This building</span><b>{t.ghg_intensity.toFixed(2)}</b><small>kg CO₂e / ft²</small></div><div className="comparison-arrow"><ArrowRight/></div><div><span>Peer median</span><b>{data.median_intensity.toFixed(2)}</b><small>across {data.peer_count} comparable buildings</small></div><div className="gap-metric"><span>Benchmark opportunity</span><b>{Math.abs(data.emissions_gap_tons).toLocaleString(undefined,{maximumFractionDigits:0})} tons</b><small>{data.emissions_gap_tons>0?'lower annual emissions at peer median':'already ahead of the median'}</small></div></div>
    <h4>Greener twins</h4><div className="twin-grid">{data.greener_twins.map((x,i)=><div key={x.property_id}><span>#{i+1}</span><b>{x.property_name}</b><small>{x.address}</small><strong>{x.ghg_intensity.toFixed(2)} <em>kg CO₂e/ft²</em></strong></div>)}</div>
    <p className="explorer-note">Comparable properties match building type and reporting year, with size and construction-year ranges widened only when necessary. This is a benchmark—not a retrofit forecast.</p>
  </div>
}

function moneyMillions(value) { return `$${Math.abs(value / 1_000_000).toFixed(1)}M` }

function BusScenarioExplorer({data}) {
  const [dieselPrice, setDieselPrice] = useState(data?.january_diesel_price || 3.52)
  const [electricityPrice, setElectricityPrice] = useState(data?.electricity_price || .1966)
  const [stressQuestion, setStressQuestion] = useState('You recommend electric buses. Under what conditions does that recommendation stop making financial sense?')
  const [stressResult, setStressResult] = useState(null)
  const [stressLoading, setStressLoading] = useState(false)
  const [stressError, setStressError] = useState('')
  useEffect(() => {
    if (data) { setDieselPrice(data.january_diesel_price); setElectricityPrice(data.electricity_price) }
  }, [data])
  if (!data) return <article className="data-card wide scenario-card"><div className="scenario-skeleton">Loading the bus scenario…</div></article>

  const dieselCost = data.diesel_gallons * dieselPrice
  const electricCost = data.electric_kwh * electricityPrice
  const savings = dieselCost - electricCost
  const maxCost = Math.max(dieselCost, electricCost, 1)
  const isSaving = savings >= 0

  async function runStressTest() {
    setStressLoading(true); setStressError(''); setStressResult(null)
    try {
      const response = await fetch('/api/bus/stress-test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:stressQuestion,diesel_price:dieselPrice,electricity_price:electricityPrice,kwh_per_mile:data.electric_kwh_per_mile})})
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Unable to run the stress test.')
      setStressResult(body)
    } catch (e) { setStressError(e.message) } finally { setStressLoading(false) }
  }

  return <article className="data-card wide scenario-card">
    <header className="scenario-heading">
      <div><span>INTERACTIVE BUDGET SCENARIO</span><h2>What happens when diesel prices move?</h2><p>Move the assumptions. The chart recalculates annual energy spending for the same FY2024 bus travel.</p></div>
      <div className="scenario-badge"><TrendingUp size={16}/> Live model</div>
    </header>

    <div className="history-grid">
      <MiniLineChart title="U.S. retail diesel" unit="$/gallon" data={data.diesel_history} color="#f06e3c" />
      <MiniLineChart title="WTI crude oil" unit="$/barrel" data={data.wti_history} color="#146b4a" />
    </div>

    <div className="scenario-layout">
      <div className="controls-panel">
        <div className="control-title"><Fuel size={18}/><div><b>Diesel price</b><small>Retail price per gallon</small></div><output>${dieselPrice.toFixed(2)}</output></div>
        <input className="scenario-slider diesel-slider" type="range" min="2" max="9" step="0.01" value={dieselPrice} onChange={e=>setDieselPrice(Number(e.target.value))} aria-label="Diesel price per gallon" style={{'--range-progress':`${(dieselPrice-2)/7*100}%`}}/>
        <div className="range-labels"><span>$2.00</span><span>$9.00</span></div>
        <div className="preset-row"><button onClick={()=>setDieselPrice(data.january_diesel_price)}>Jan actual · ${data.january_diesel_price.toFixed(2)}</button><button onClick={()=>setDieselPrice(data.september_diesel_price)}>Sep actual · ${data.september_diesel_price.toFixed(2)}</button></div>

        <div className="control-title secondary-control"><Zap size={18}/><div><b>Electricity price</b><small>New York average per kWh</small></div><output>${electricityPrice.toFixed(2)}</output></div>
        <input className="scenario-slider electric-slider" type="range" min="0.10" max="0.35" step="0.005" value={electricityPrice} onChange={e=>setElectricityPrice(Number(e.target.value))} aria-label="Electricity price per kilowatt-hour" style={{'--range-progress':`${(electricityPrice-.1)/.25*100}%`}}/>
        <div className="range-labels"><span>$0.10</span><span>$0.35</span></div>
      </div>

      <div className="cost-visual">
        <div className="cost-summary"><span>Modeled annual energy-cost difference</span><strong className={isSaving?'positive':'negative'}>{moneyMillions(savings)} {isSaving?'lower':'higher'}</strong><small>for electric operation under these assumptions</small></div>
        <div className="cost-bars">
          <div className="cost-row"><div><Fuel size={17}/><span>Diesel fleet</span></div><div className="cost-track"><i className="diesel-cost" style={{width:`${dieselCost/maxCost*100}%`}}></i></div><b>{moneyMillions(dieselCost)}</b></div>
          <div className="cost-row"><div><Zap size={17}/><span>Electric fleet</span></div><div className="cost-track"><i className="electric-cost" style={{width:`${electricCost/maxCost*100}%`}}></i></div><b>{moneyMillions(electricCost)}</b></div>
        </div>
        <div className="scenario-insights">
          <div><DollarSign/><span><b>{(data.diesel_gallons/1_000_000).toFixed(1)}M gallons</b><small>FY2024 diesel baseline</small></span></div>
          <div><Zap/><span><b>{Math.round(data.electric_kwh/1_000_000)}M kWh</b><small>modeled electric use</small></span></div>
          <div><Leaf/><span><b>{Math.round(data.co2_reduction_tons/1000)}K tons</b><small>operational CO₂ reduction</small></span></div>
        </div>
      </div>
    </div>
    <section className="stress-lab">
      <div className="stress-intro"><div className="natural-label"><Gauge size={18}/><span><b>What would change your mind?</b><small>Ask Mistral to choose the toughest assumption. Python calculates the break-even point.</small></span></div></div>
      <div className="stress-input"><input value={stressQuestion} onChange={e=>setStressQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')runStressTest()}} aria-label="Ask a bus recommendation stress-test question"/><button onClick={runStressTest} disabled={stressLoading||!stressQuestion.trim()}>{stressLoading?<LoaderCircle className="spin"/>:<Sparkles/>}{stressLoading?'Stress-testing…':'Challenge the recommendation'}</button></div>
      {stressError&&<p className="inline-error">{stressError}</p>}
      {stressResult&&<StressTestResult result={stressResult}/>}
    </section>
    <p className="scenario-note"><ShieldCheck size={15}/> Energy only—not a total-cost forecast. Bus purchases, chargers, depots, financing, maintenance, batteries and demand charges are excluded. WTI and diesel use different units and are shown as separate trends.</p>
  </article>
}

function StressTestResult({result}) {
  const isPower = result.selected_test==='electricity_ceiling'
  const isEfficiency = result.selected_test==='bus_efficiency'
  const curve = isPower ? result.electricity_curve : isEfficiency ? result.efficiency_curve : result.diesel_curve
  const xKey = isPower ? 'electricity_price' : isEfficiency ? 'kwh_per_mile' : 'diesel_price'
  const label = isPower ? 'Electricity price ($/kWh)' : isEfficiency ? 'Bus energy use (kWh/mile)' : 'Diesel price ($/gallon)'
  const values = curve.map(x=>x.savings_millions)
  const maxAbs = Math.max(...values.map(Math.abs),1)
  const points = curve.map((x,i)=>`${6+i*(88/(curve.length-1))},${50-(x.savings_millions/maxAbs)*38}`).join(' ')
  const finding = result.selected_test==='electricity_ceiling'
    ? `Electric energy loses its modeled operating-cost advantage above $${result.break_even_electricity_price.toFixed(3)}/kWh in the ${result.reference_case} case.`
    : result.selected_test==='bus_efficiency'
      ? `The modeled bus could use up to ${result.break_even_kwh_per_mile.toFixed(2)} kWh/mile before electric energy costs equal diesel in the ${result.reference_case} case.`
      : `Diesel would need to fall to about $${result.break_even_diesel_price.toFixed(3)}/gallon before the modeled energy costs are equal.`
  return <div className="stress-result">
    <div className="mistral-interpretation"><Sparkles size={15}/><span><b>Mistral selected:</b> {result.selected_test.replaceAll('_',' ')} using the {result.reference_case} case. {result.mistral_rationale}</span></div>
    <div className="stress-grid">
      <div className="stress-finding"><span>BREAK-EVEN FINDING</span><h3>{finding}</h3><p>At the selected reference assumptions, electric operation is <b>${Math.abs(result.current_savings_millions).toFixed(1)}M {result.current_savings_millions>=0?'lower':'higher'}</b> in annual energy spending.</p></div>
      <div className="break-even-chart"><div className="chart-title"><span>{label}</span><b>Annual energy-cost advantage</b></div><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Break-even sensitivity curve"><line x1="6" y1="50" x2="94" y2="50" className="zero-line"/><polygon points={`6,50 ${points} 94,50`} className="stress-area"/><polyline points={points} className="stress-line" vectorEffect="non-scaling-stroke"/></svg><div className="stress-axis"><span>{curve[0][xKey].toFixed(2)}</span><span>break-even</span><span>{curve[curve.length-1][xKey].toFixed(2)}</span></div></div>
    </div>
    <div className="break-even-cards"><div><Fuel/><span><small>Diesel floor</small><b>${result.break_even_diesel_price.toFixed(3)}/gal</b></span></div><div><Zap/><span><small>Power ceiling</small><b>${result.break_even_electricity_price.toFixed(3)}/kWh</b></span></div><div><Gauge/><span><small>Efficiency ceiling</small><b>{result.break_even_kwh_per_mile.toFixed(2)} kWh/mi</b></span></div></div>
    <p className="stress-scope">{result.scope}</p>
  </div>
}

function MiniLineChart({title, unit, data=[], color}) {
  const values = data.map(d=>d.value)
  const min = Math.min(...values), max = Math.max(...values), spread = max-min || 1
  const points = data.map((d,i)=>`${data.length===1?50:5+i*(90/(data.length-1))},${80-((d.value-min)/spread)*58}`).join(' ')
  const last = data[data.length-1]
  return <div className="mini-chart">
    <div className="mini-chart-head"><div><b>{title}</b><span>{unit} · {data.length <= 2 ? 'verified Jan & Sep 2026 averages' : 'monthly Jan–Sep 2026'}</span></div>{last&&<strong style={{color}}>${last.value.toFixed(2)}</strong>}</div>
    <svg viewBox="0 0 100 92" preserveAspectRatio="none" role="img" aria-label={`${title} monthly price trend`}>
      <defs><linearGradient id={`fill-${title.replaceAll(' ','-')}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".28"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <line x1="5" y1="80" x2="95" y2="80" className="chart-grid"/><line x1="5" y1="51" x2="95" y2="51" className="chart-grid"/><line x1="5" y1="22" x2="95" y2="22" className="chart-grid"/>
      {points&&<><polygon points={`5,80 ${points} 95,80`} fill={`url(#fill-${title.replaceAll(' ','-')})`}/><polyline points={points} fill="none" stroke={color} strokeWidth="2.2" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round"/></>}
      {data.map((d,i)=><circle key={d.month} cx={data.length===1?50:5+i*(90/(data.length-1))} cy={80-((d.value-min)/spread)*58} r="1.7" fill="#fff" stroke={color} strokeWidth="1.2" vectorEffect="non-scaling-stroke"><title>{d.month}: ${d.value.toFixed(2)}</title></circle>)}
    </svg>
    <div className="chart-axis">{data.map(d=><span key={d.month}>{d.month}</span>)}</div>
  </div>
}

function Metric({icon:Icon,value,label,note}) { return <article className="metric-card"><span className="metric-icon"><Icon/></span><b>{value}</b><h3>{label}</h3><p>{note}</p></article> }

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>)
