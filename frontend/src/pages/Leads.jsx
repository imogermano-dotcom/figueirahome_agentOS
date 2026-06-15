import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const ESTADOS = ['novo', 'contactado', 'visita', 'proposta', 'fechado', 'perdido']

const estadoBadge = {
  novo: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
  contactado: 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
  visita: 'bg-violet-500/15 text-violet-400 border border-violet-500/20',
  proposta: 'bg-orange-500/15 text-orange-400 border border-orange-500/20',
  fechado: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  perdido: 'bg-zinc-700 text-zinc-500',
}

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"
const selectCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500 transition-colors"

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <h2 className="font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-xl leading-none transition-colors">×</button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

export default function Leads() {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [estadoFiltro, setEstadoFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ estado: 'novo', notas: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (estadoFiltro) params.set('estado', estadoFiltro)
    try { setLeads(await api.get(`/api/leads?${params}`)) }
    catch { setError('Erro ao carregar leads.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [estadoFiltro])

  function openEdit(lead) { setForm({ estado: lead.estado||'novo', notas: lead.notas||'' }); setModal(lead) }

  async function handleSave(e) {
    e.preventDefault(); setSaving(true)
    try { await api.put(`/api/leads/${modal.id}`, form); setModal(null); load() }
    catch (err) { setError(err.message) }
    setSaving(false)
  }

  async function handleDelete(id) {
    if (!confirm('Apagar este lead?')) return
    try { await api.delete(`/api/leads/${id}`); load() }
    catch (err) { setError(err.message) }
  }

  function formatDate(iso) {
    if (!iso) return '—'
    return new Date(iso).toLocaleDateString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Leads</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{leads.length} lead{leads.length !== 1 ? 's' : ''}</p>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="flex gap-3 mb-4">
        <select value={estadoFiltro} onChange={e => setEstadoFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors">
          <option value="">Todos os estados</option>
          {ESTADOS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
        </select>
      </div>

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-zinc-500 text-xs uppercase tracking-widest">
              <th className="px-4 py-3">Cliente</th>
              <th className="px-4 py-3">Telefone</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Notas</th>
              <th className="px-4 py-3">Data</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && leads.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">Sem leads.</td></tr>}
            {leads.map(lead => (
              <tr key={lead.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">{lead.agente_clientes?.nome || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{lead.agente_clientes?.telefone || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${estadoBadge[lead.estado] || 'bg-zinc-700 text-zinc-400'}`}>{lead.estado}</span>
                </td>
                <td className="px-4 py-3 text-zinc-400 max-w-xs truncate">{lead.notas || '—'}</td>
                <td className="px-4 py-3 text-zinc-600 text-xs">{formatDate(lead.criado_em)}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => openEdit(lead)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Editar</button>
                    <button onClick={() => handleDelete(lead.id)} className="text-xs text-red-500 hover:text-red-400 transition-colors">Apagar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title="Editar lead" onClose={() => setModal(null)}>
          <form onSubmit={handleSave} className="space-y-4">
            <p className="text-sm text-zinc-500">Cliente: <span className="font-medium text-zinc-200">{modal.agente_clientes?.nome || '—'}</span></p>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Estado</label>
              <select className={selectCls} value={form.estado} onChange={e => setForm(f => ({ ...f, estado: e.target.value }))}>
                {ESTADOS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Notas</label>
              <textarea className={inputCls} rows={3} value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button type="button" onClick={() => setModal(null)} className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors">Cancelar</button>
              <button type="submit" disabled={saving} className="bg-gradient-to-r from-blue-600 to-blue-700 text-white text-sm font-medium px-5 py-2 rounded-lg disabled:opacity-50 transition-all">
                {saving ? 'A guardar…' : 'Guardar'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
