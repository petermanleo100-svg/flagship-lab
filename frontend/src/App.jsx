import { useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_BASE || '/api'
const samples = [
  { invoice_id: 'INV-2026-0001', seller_tax_id: null, buyer_tax_id: 'BUYER-001', invoice_date: '2026-08-01', amount: '1000.0000', tax_rate: '0.130000', tax_amount: '130.0000', currency: 'CNY' },
  { invoice_id: 'INV-2026-0002', seller_tax_id: 'SELLER-001', buyer_tax_id: 'BUYER-001', invoice_date: '2026-08-02', amount: '800.0000', tax_rate: '0.130000', tax_amount: '99.0000', currency: 'CNY' },
]

function App() {
  const [health, setHealth] = useState('检查中')
  const [token, setToken] = useState(() => sessionStorage.getItem('flagship_token') || '')
  const [subject, setSubject] = useState('chen-shaokai')
  const [tenant, setTenant] = useState('portfolio')
  const [role, setRole] = useState('admin')
  const [transactions, setTransactions] = useState(JSON.stringify(samples, null, 2))
  const [run, setRun] = useState(null)
  const [findings, setFindings] = useState([])
  const [cases, setCases] = useState([])
  const [audit, setAudit] = useState(null)
  const [message, setMessage] = useState('连接后即可执行真实 API 工作流。')
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])

  useEffect(() => { fetch(`${API}/health/ready`).then(r => r.json().then(data => ({ r, data })))
    .then(({ r, data }) => setHealth(r.ok ? `就绪 · ${data.dialect}` : '依赖异常')).catch(() => setHealth('API 离线')) }, [])

  async function request(path, options = {}) {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } })
    const data = (response.headers.get('content-type') || '').includes('json') ? await response.json() : await response.text()
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`)
    return data
  }

  async function login(event) {
    event.preventDefault()
    try {
      const response = await fetch(`${API}/auth/dev-token`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ subject, tenant_id: tenant, roles: [role], ttl_minutes: 60 }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '开发令牌端点未启用')
      sessionStorage.setItem('flagship_token', data.access_token); setToken(data.access_token)
      setMessage(`已连接租户 ${tenant}，角色 ${role}。令牌仅保存在当前标签页。`)
    } catch (error) { setMessage(error.message) }
  }

  async function ingestAndRun() {
    try {
      const seed = crypto.randomUUID()
      await request('/tax/transactions', { method: 'POST', headers: { 'Idempotency-Key': `ui-import-${seed}` }, body: JSON.stringify(JSON.parse(transactions)) })
      const result = await request('/tax/runs', { method: 'POST', headers: { 'Idempotency-Key': `ui-run-${seed}` }, body: '{}' })
      setRun(result); setFindings(await request(`/tax/findings?run_id=${result.run_id}`)); setMessage('规则运行完成，发现已进入独立复核队列。')
    } catch (error) { setMessage(error.message) }
  }

  async function review(decision) {
    try {
      const result = await request(`/tax/runs/${run.run_id}/review`, { method: 'POST', body: JSON.stringify({ decision, comment: '工作台独立复核：已检查规则版本、异常样本与审计记录。' }) })
      setRun(current => ({ ...current, workflow: result })); setMessage(`复核已完成：${result.status}`)
    } catch (error) { setMessage(error.message) }
  }

  async function refreshGovernance() {
    try { const [caseData, auditData] = await Promise.all([request('/controls/cases'), request('/audit/verify')]); setCases(caseData); setAudit(auditData); setMessage('治理视图已刷新。') }
    catch (error) { setMessage(error.message) }
  }

  return <main><header><div><p className="eyebrow">FLAGSHIP LAB · ENTERPRISE WORKBENCH</p><h1>审计工作台</h1><p>税务规则、控制案例与证据链的真实 API 操作界面</p></div><span className="health">● {health}</span></header>
    <div className="notice">{message}</div><section className="grid">
      <article><h2>01 · 身份与租户</h2><form onSubmit={login}><label>用户<input value={subject} onChange={e => setSubject(e.target.value)} /></label><label>租户<input value={tenant} onChange={e => setTenant(e.target.value)} /></label><label>角色<select value={role} onChange={e => setRole(e.target.value)}><option>admin</option><option>analyst</option><option>reviewer</option><option>viewer</option></select></label><button>获取本地开发令牌</button></form><small>生产环境由 OIDC/JWKS 登录替换；工作台不持久化令牌。</small></article>
      <article className="wide"><h2>02 · TaxFlow 规则运行</h2><textarea value={transactions} onChange={e => setTransactions(e.target.value)} spellCheck="false" /><div className="actions"><button disabled={!token} onClick={ingestAndRun}>幂等导入并运行规则</button>{run && <><button className="secondary" onClick={() => review('APPROVE')}>批准</button><button className="danger" onClick={() => review('REJECT')}>拒绝</button></>}</div>{run && <dl><div><dt>运行 ID</dt><dd>{run.run_id}</dd></div><div><dt>规则版本</dt><dd>{run.rule_version}</dd></div><div><dt>状态</dt><dd>{run.workflow?.status || 'PENDING_REVIEW'}</dd></div></dl>}</article>
      <article><h2>03 · 异常发现</h2><strong className="metric">{findings.length}</strong><p>当前规则运行的证据化发现</p><ul>{findings.slice(0, 5).map(item => <li key={item.id}><b>{item.rule_code}</b><span>{item.invoice_id} · {item.severity}</span></li>)}</ul></article>
      <article><h2>04 · 治理状态</h2><button disabled={!token} onClick={refreshGovernance}>刷新治理视图</button><dl><div><dt>开放控制案例</dt><dd>{cases.length}</dd></div><div><dt>审计链</dt><dd>{audit ? (audit.valid ? `有效 · ${audit.events} 事件` : '已断裂') : '未检查'}</dd></div></dl></article>
    </section><footer>所有结果来自当前 API 与当前租户；合成样本不代表真实税务或风险识别效果。</footer></main>
}
export default App
