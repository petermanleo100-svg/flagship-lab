import { useEffect, useState } from 'react'

const modules = [
  { name: 'TaxFlow Nexus', eyebrow: 'TAX TECHNOLOGY', metric: '43,324.53', unit: 'rows / sec', detail: '100K synthetic transactions · versioned JSON rule pack · tamper-evident ZIP', tone: 'cyan' },
  { name: 'RegIntel Copilot', eyebrow: 'REGULATORY AI', metric: '1.000', unit: 'Recall@3', detail: '8 synthetic documents · 12 queries · lexical + char TF-IDF hybrid retrieval', tone: 'violet' },
  { name: 'ControlPulse', eyebrow: 'CONTINUOUS CONTROLS', metric: '3 → 5', unit: 'events → cases', detail: 'Hash-chained JSONL · atomic checkpoint · idempotent replay', tone: 'amber' },
  { name: 'RiskGraph Investigator', eyebrow: 'GRAPH RISK', metric: '0.8627', unit: 'PR-AUC', detail: '1,600 temporal holdout rows · Recall@Top5% 0.8372 · model card', tone: 'lime' },
]

const roles = [
  ['viewer', 'Read findings and evidence-backed answers'],
  ['analyst', 'Ingest data, execute rules and controls'],
  ['reviewer', 'Verify audit chain and export evidence'],
  ['admin', 'Full access and configuration checks'],
]

function App() {
  const [health, setHealth] = useState({ state: 'checking', label: 'Checking API' })
  const api = import.meta.env.VITE_API_BASE || '/api'
  useEffect(() => {
    fetch(`${api}/health`).then(r => r.ok ? r.json() : Promise.reject()).then(data => setHealth({ state: 'online', label: `API ${data.version || 'online'}` })).catch(() => setHealth({ state: 'offline', label: 'Offline evidence mode' }))
  }, [api])
  return <main>
    <header className="hero">
      <nav><span className="brand">FLAGSHIP<span>LAB</span></span><span className={`status ${health.state}`}><i />{health.label}</span></nav>
      <div className="hero-grid">
        <div><p className="kicker">AUDITABLE ENGINEERING PORTFOLIO · PHASE 2</p><h1>Evidence first.<br/><em>Claims second.</em></h1></div>
        <p className="lede">Four professional-services systems built around traceability, separation of duties, reproducible evaluation and explicit limitations.</p>
      </div>
    </header>

    <section className="module-grid" aria-label="Project evidence metrics">
      {modules.map((item, index) => <article className={`module ${item.tone}`} key={item.name}>
        <div className="module-top"><span>0{index + 1}</span><p>{item.eyebrow}</p></div>
        <h2>{item.name}</h2><div className="metric">{item.metric}<small>{item.unit}</small></div><p className="detail">{item.detail}</p>
      </article>)}
    </section>

    <section className="evidence">
      <div><p className="kicker">CONTROL DESIGN</p><h2>One platform, distinct duties.</h2><p>JWT roles are enforced at API boundaries. The analyst who runs a rule cannot download the final evidence package unless separately granted reviewer authority.</p></div>
      <div className="role-list">{roles.map(([role, desc]) => <div key={role}><code>{role}</code><span>{desc}</span></div>)}</div>
    </section>

    <section className="proof">
      <p className="kicker">VERIFICATION CHAIN</p>
      <div className="steps"><span>INGEST</span><b>→</b><span>VERSION</span><b>→</b><span>DETECT</span><b>→</b><span>REVIEW</span><b>→</b><span>HASH</span></div>
      <p>All displayed metrics come from fixed commands and synthetic datasets. They demonstrate engineering behavior—not production tax, legal or fraud-detection accuracy.</p>
    </section>
    <footer><span>Flagship Lab · 2026</span><span>FastAPI · PostgreSQL · React · scikit-learn</span></footer>
  </main>
}

export default App
