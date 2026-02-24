import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { Line } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend } from 'chart.js'
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options)
  const text = await res.text()
  let data = {}
  try { data = text ? JSON.parse(text) : {} } catch { data = { detail: text } }
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data))
  return data
}

function useToast() {
  const [msg, setMsg] = useState('')
  return { msg, show: (m) => { setMsg(m); setTimeout(() => setMsg(''), 4000) } }
}

function Layout({ children }) {
  return <div style={{ fontFamily: 'sans-serif', padding: 16 }}>
    <h2>Energy Pattern Analyzer MVP</h2>
    <div style={{ marginBottom: 10, display: 'flex', gap: 8 }}><Link to='/'>Devices</Link></div>
    {children}
  </div>
}

function DevicesPage() {
  const [devices, setDevices] = useState([])
  const [statusMap, setStatusMap] = useState({})
  const nav = useNavigate()
  const t = useToast()
  const [form, setForm] = useState({ name: '', type: 'power', source_type: 'csv', main_metric: 'watts', shelly_host: '' })

  const load = async () => {
    const d = await api('/devices')
    setDevices(d)
    const map = {}
    for (const x of d) {
      try {
        const s = await api(`/devices/${x.id}/stats`)
        let current = 'N/A'
        try { current = (await api(`/devices/${x.id}/status/current?window_sec=600`)).state } catch { }
        map[x.id] = { stats: s, current }
      } catch { }
    }
    setStatusMap(map)
  }
  useEffect(() => { load() }, [])

  return <Layout>
    {t.msg && <div style={{ background: '#fee', padding: 8, marginBottom: 8 }}>{t.msg}</div>}
    <div style={{ border: '1px solid #ccc', padding: 8, marginBottom: 12 }}>
      <b>Add device</b>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 6 }}>
        <input placeholder='name' value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}><option>power</option><option>light</option><option>lux</option><option>other</option></select>
        <select value={form.source_type} onChange={e => setForm({ ...form, source_type: e.target.value })}><option>csv</option><option>shelly</option></select>
        <select value={form.main_metric} onChange={e => setForm({ ...form, main_metric: e.target.value })}><option>watts</option><option>on</option><option>lux</option></select>
        <input placeholder='shelly host optional' value={form.shelly_host} onChange={e => setForm({ ...form, shelly_host: e.target.value })} />
        <button onClick={async () => {
          try {
            await api('/devices', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
            setForm({ ...form, name: '' }); load()
          } catch (e) { t.show(e.message) }
        }}>Create</button>
      </div>
    </div>

    {devices.map(d => <div key={d.id} style={{ border: '1px solid #ddd', marginBottom: 6, padding: 8, cursor: 'pointer' }} onClick={() => nav(`/devices/${d.id}`)}>
      <b>#{d.id} {d.name}</b> | {d.type}/{d.main_metric} | state: {statusMap[d.id]?.current || 'N/A'} | points: {statusMap[d.id]?.stats?.count || 0}
    </div>)}
  </Layout>
}

function DeviceDetail() {
  const { id } = useParams()
  const t = useToast()
  const [device, setDevice] = useState(null)
  const [series, setSeries] = useState([])
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [proposal, setProposal] = useState(null)
  const [ruleForm, setRuleForm] = useState({ name: 'proposed-rule', states: [] })
  const [sim, setSim] = useState(null)
  const [rules, setRules] = useState([])
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadAll = async () => {
    const d = await api(`/devices/${id}`)
    setDevice(d)
    const s = await api(`/devices/${id}/series?downsample_sec=30${from ? `&from_ts=${from}` : ''}${to ? `&to_ts=${to}` : ''}`)
    setSeries(s)
    setRules(await api(`/devices/${id}/rules`))
    try { setStatus(await api(`/devices/${id}/status/current?window_sec=600`)) } catch { setStatus(null) }
  }
  useEffect(() => { loadAll() }, [id])

  const chartData = useMemo(() => ({
    labels: series.map(x => x.ts.slice(11, 19)),
    datasets: [{ label: device?.main_metric || 'metric', data: series.map(x => x[device?.main_metric || 'watts'] || 0), borderColor: '#36a', pointRadius: 0 }]
  }), [series, device])

  if (!device) return <Layout>Loading...</Layout>
  return <Layout>
    {t.msg && <div style={{ background: '#fee', padding: 8 }}>{t.msg}</div>}
    <h3>{device.name} (#{device.id})</h3>
    <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
      <input type='datetime-local' value={from} onChange={e => setFrom(e.target.value)} />
      <input type='datetime-local' value={to} onChange={e => setTo(e.target.value)} />
      <button onClick={loadAll}>Refresh window</button>
    </div>
    <Line data={chartData} />

    <div style={{ marginTop: 12, border: '1px solid #ddd', padding: 8 }}>
      <b>Ingest CSV (Shelly-like fixed)</b>
      <input type='file' onChange={async e => {
        const f = e.target.files[0]; if (!f) return
        try {
          setLoading(true)
          const fd = new FormData(); fd.append('file', f)
          await api(`/devices/${id}/ingest/csv?timezone_name=Europe/Paris`, { method: 'POST', body: fd })
          await loadAll()
        } catch (e) { t.show(e.message) } finally { setLoading(false) }
      }} /> {loading ? 'en cours...' : ''}
    </div>

    <div style={{ marginTop: 12, border: '1px solid #ddd', padding: 8 }}>
      <b>Pull Shelly</b>
      <button onClick={async () => {
        try {
          await api(`/devices/${id}/ingest/shelly_pull`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_ts: new Date(Date.now() - 3600_000).toISOString(), to_ts: new Date().toISOString(), interval_sec: 30 })
          })
          loadAll()
        } catch (e) { t.show(e.message) }
      }}>Pull last hour</button>
    </div>

    <div style={{ marginTop: 12, border: '1px solid #ddd', padding: 8 }}>
      <button onClick={async () => {
        try {
          const r = await api(`/devices/${id}/analyze/oneshot`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_ts: from || null, to_ts: to || null }) })
          setProposal(r)
          setRuleForm({ name: 'proposed-rule', states: r.proposed_rule.states, json: r.proposed_rule })
        } catch (e) { t.show(e.message) }
      }}>Analyze oneshot</button>
      {proposal && <div>
        <div>Score: {proposal.score} | {proposal.explanations}</div>
        {ruleForm.states.map((s, i) => <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 4 }}>
          <input value={s.name} onChange={e => { const x = [...ruleForm.states]; x[i].name = e.target.value; setRuleForm({ ...ruleForm, states: x }) }} />
          <select value={s.when.op} onChange={e => { const x = [...ruleForm.states]; x[i].when.op = e.target.value; setRuleForm({ ...ruleForm, states: x }) }}><option>gte</option><option>lte</option><option>between</option></select>
          <input value={s.when.value ?? s.when.min} onChange={e => { const x = [...ruleForm.states]; if (x[i].when.op === 'between') x[i].when.min = Number(e.target.value); else x[i].when.value = Number(e.target.value); setRuleForm({ ...ruleForm, states: x }) }} />
          <input value={s.when.for_sec} onChange={e => { const x = [...ruleForm.states]; x[i].when.for_sec = Number(e.target.value); setRuleForm({ ...ruleForm, states: x }) }} />
        </div>)}
        <textarea rows={8} style={{ width: '100%' }} value={JSON.stringify({ ...proposal.proposed_rule, states: ruleForm.states }, null, 2)} onChange={(e) => {
          try { const j = JSON.parse(e.target.value); setRuleForm({ ...ruleForm, states: j.states, json: j }) } catch { }
        }} />
        <button onClick={async () => {
          try {
            const json = ruleForm.json || { ...proposal.proposed_rule, states: ruleForm.states }
            const s = await api(`/devices/${id}/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_ts: from || null, to_ts: to || null, rule_json: json }) })
            setSim(s)
          } catch (e) { t.show(e.message) }
        }}>Simulate</button>
        <button onClick={async () => {
          try {
            const json = ruleForm.json || { ...proposal.proposed_rule, states: ruleForm.states }
            const created = await api(`/devices/${id}/rules`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: ruleForm.name, json }) })
            await api(`/rules/${created.id}/activate`, { method: 'POST' })
            loadAll(); t.show('Rule activated')
          } catch (e) { t.show(e.message) }
        }}>Publish + Activate</button>
      </div>}
    </div>

    {status && <div style={{ marginTop: 12, border: '1px solid #ddd', padding: 8 }}>Current: <b>{status.state}</b> last event: {status.last_event?.type || 'none'}</div>}
    {sim && <div style={{ marginTop: 12, border: '1px solid #ddd', padding: 8 }}>
      <b>Timeline events</b>
      {sim.events.slice(-20).map((e, i) => <div key={i}>{e.ts} - {e.type} - {JSON.stringify(e.payload)}</div>)}
    </div>}
    <div style={{ marginTop: 12 }}><Link to={`/devices/${id}/rules`}>Rules management</Link></div>
  </Layout>
}

function RulesPage() {
  const { id } = useParams()
  const [rules, setRules] = useState([])
  const t = useToast()
  const load = async () => setRules(await api(`/devices/${id}/rules`))
  useEffect(() => { load() }, [id])
  return <Layout>
    {t.msg && <div style={{ background: '#fee', padding: 8 }}>{t.msg}</div>}
    <h3>Rules device #{id}</h3>
    {rules.map(r => <div key={r.id} style={{ border: '1px solid #ddd', marginBottom: 8, padding: 8 }}>
      <b>{r.name}</b> {r.is_active ? '(active)' : ''}
      <button onClick={async () => { await api(`/rules/${r.id}/activate`, { method: 'POST' }); load() }}>activate</button>
      <button onClick={async () => {
        await api(`/devices/${id}/rules`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: `${r.name}-copy`, json: r.json }) })
        load()
      }}>duplicate</button>
    </div>)}
  </Layout>
}

function App() {
  return <BrowserRouter><Routes>
    <Route path='/' element={<DevicesPage />} />
    <Route path='/devices/:id' element={<DeviceDetail />} />
    <Route path='/devices/:id/rules' element={<RulesPage />} />
  </Routes></BrowserRouter>
}

createRoot(document.getElementById('root')).render(<App />)
