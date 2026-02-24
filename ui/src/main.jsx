import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Layout({ children }) {
  return <div style={{fontFamily:'sans-serif',padding:20}}>
    <h2>Energy Pattern Analyzer</h2>
    <nav style={{display:'flex',gap:12,marginBottom:16}}>
      <Link to="/">Devices</Link>
      <Link to="/config">Config</Link>
    </nav>
    {children}
  </div>
}

function DevicesPage() {
  const [devices,setDevices]=useState([])
  const nav=useNavigate()
  useEffect(()=>{fetch(`${API}/devices`).then(r=>r.json()).then(setDevices)},[])
  return <Layout>
    <button onClick={async()=>{
      const id=`device_${Date.now()}`
      await fetch(`${API}/devices`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,name:`Device ${devices.length+1}`,type:'other',metrics:['watts'],source_config:{}})})
      setDevices(await (await fetch(`${API}/devices`)).json())
    }}>+ Add device</button>
    <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))',gap:12,marginTop:12}}>
      {devices.map(d=><div key={d.id} style={{border:'1px solid #ddd',padding:10,borderRadius:8,cursor:'pointer'}} onClick={()=>nav(`/devices/${d.id}`)}>
        <b>{d.name}</b><div>{d.type}</div><small>{d.metrics.join(', ')}</small>
      </div>)}
    </div>
  </Layout>
}

function DeviceDetail(){
  const {id}=useParams();
  const [series,setSeries]=useState([])
  const [proposal,setProposal]=useState(null)
  const [sim,setSim]=useState(null)
  useEffect(()=>{fetch(`${API}/series?device_id=${id}&metric=watts`).then(r=>r.json()).then(setSeries)},[id])
  const spark = useMemo(()=>series.slice(-30).map(x=>x.value),[series])
  return <Layout>
    <h3>Device {id}</h3>
    <pre style={{background:'#f7f7f7',padding:8}}>Sparkline data: {JSON.stringify(spark)}</pre>
    <div style={{display:'flex',gap:10}}>
      <button onClick={async()=>setProposal(await (await fetch(`${API}/analyze/oneshot`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device_id:id,metric:'watts'})})).json())}>Proposer des règles</button>
      <button onClick={async()=>{
        if(!proposal) return
        const saved=await (await fetch(`${API}/rules`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device_id:id,name:'auto-rule',dsl:proposal.dsl,explanation:proposal.explanation,confidence:proposal.confidence})})).json()
        setSim(await (await fetch(`${API}/simulate`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device_id:id,rule_id:saved.id,metric:'watts'})})).json())
      }}>Publier + Simuler</button>
    </div>
    {proposal && <pre style={{background:'#eef',padding:8}}>Règle proposée: {JSON.stringify(proposal,null,2)}</pre>}
    {sim && <pre style={{background:'#efe',padding:8}}>Simulation: {JSON.stringify(sim,null,2)}</pre>}
  </Layout>
}

function ConfigPage(){
  const [cfg,setCfg]=useState({})
  useEffect(()=>{fetch(`${API}/config/effective`).then(r=>r.json()).then(setCfg)},[])
  return <Layout><pre>{JSON.stringify(cfg,null,2)}</pre></Layout>
}

function App(){
  return <BrowserRouter><Routes>
    <Route path="/" element={<DevicesPage/>}/>
    <Route path="/devices/:id" element={<DeviceDetail/>}/>
    <Route path="/config" element={<ConfigPage/>}/>
  </Routes></BrowserRouter>
}

createRoot(document.getElementById('root')).render(<App />)
