import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const TIPOS = ['compra', 'arrendamento', 'venda', 'outro']
const ORIGENS = ['chamada', 'whatsapp', 'manual', 'chat']
const EMPTY_FORM = {
  nome: '', telefone: '', email: '', tipo_interesse: '',
  orcamento: '', zona_preferida: '', notas: '', origem: 'manual',
}

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"
const selectCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500 transition-colors"

const tipoLabel = { compra: 'Compra', arrendamento: 'Arrendamento', venda: 'Venda', outro: 'Outro' }
const tipoBadge = {
  compra: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
  arrendamento: 'bg-violet-500/15 text-violet-400 border border-violet-500/20',
  venda: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  outro: 'bg-zinc-700 text-zinc-400',
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <h2 className="font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 text-xl leading-none transition-colors">×</button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  )
}

export default function Clientes() {
  const [clientes, setClientes] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tipoFiltro, setTipoFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (tipoFiltro) params.set('tipo', tipoFiltro)
    try {
      setClientes(await api.get(`/api/clientes?${params}`))
    } catch { setError('Erro ao carregar clientes.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [search, tipoFiltro])

  function openNew() { setForm(EMPTY_FORM); setModal('new') }
  function openEdit(c) {
    setForm({ nome: c.nome||'', telefone: c.telefone||'', email: c.email||'',
      tipo_interesse: c.tipo_interesse||'', orcamento: c.orcamento??'',
      zona_preferida: c.zona_preferida||'', notas: c.notas||'', origem: c.origem||'manual' })
    setModal(c)
  }

  async function handleSave(e) {
    e.preventDefault(); setSaving(true)
    const body = { ...form, orcamento: form.orcamento ? Number(form.orcamento) : undefined }
    if (!body.orcamento) delete body.orcamento
    try {
      modal === 'new' ? await api.post('/api/clientes', body) : await api.put(`/api/clientes/${modal.id}`, body)
      setModal(null); load()
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  async function handleDelete(id) {
    if (!confirm('Apagar este cliente?')) return
    try { await api.delete(`/api/clientes/${id}`); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Clientes</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{clientes.length} registo{clientes.length !== 1 ? 's' : ''}</p>
        </div>
        <button onClick={openNew} className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20">
          + Novo cliente
        </button>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="flex gap-3 mb-4">
        <input placeholder="Pesquisar por nome…" value={search} onChange={e => setSearch(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:border-blue-500 transition-colors" />
        <select value={tipoFiltro} onChange={e => setTipoFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors">
          <option value="">Todos os tipos</option>
          {TIPOS.map(t => <option key={t} value={t}>{tipoLabel[t]}</option>)}
        </select>
      </div>

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-zinc-500 text-xs uppercase tracking-widest">
              <th className="px-4 py-3">Nome</th>
              <th className="px-4 py-3">Telefone</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">Orçamento</th>
              <th className="px-4 py-3">Zona</th>
              <th className="px-4 py-3">Origem</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && clientes.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-zinc-600">Sem clientes.</td></tr>}
            {clientes.map(c => (
              <tr key={c.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">{c.nome || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{c.telefone || '—'}</td>
                <td className="px-4 py-3">
                  {c.tipo_interesse
                    ? <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${tipoBadge[c.tipo_interesse] || 'bg-zinc-700 text-zinc-400'}`}>{tipoLabel[c.tipo_interesse]}</span>
                    : <span className="text-zinc-600">—</span>}
                </td>
                <td className="px-4 py-3 text-zinc-400">{c.orcamento ? `${Number(c.orcamento).toLocaleString('pt-PT')} €` : '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{c.zona_preferida || '—'}</td>
                <td className="px-4 py-3 text-zinc-600 text-xs">{c.origem || '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => openEdit(c)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Editar</button>
                    <button onClick={() => handleDelete(c.id)} className="text-xs text-red-500 hover:text-red-400 transition-colors">Apagar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'new' ? 'Novo cliente' : 'Editar cliente'} onClose={() => setModal(null)}>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Nome"><input className={inputCls} value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} /></Field>
              <Field label="Telefone"><input className={inputCls} value={form.telefone} onChange={e => setForm(f => ({ ...f, telefone: e.target.value }))} /></Field>
              <Field label="Email"><input type="email" className={inputCls} value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} /></Field>
              <Field label="Tipo de interesse">
                <select className={selectCls} value={form.tipo_interesse} onChange={e => setForm(f => ({ ...f, tipo_interesse: e.target.value }))}>
                  <option value="">— seleccionar —</option>
                  {TIPOS.map(t => <option key={t} value={t}>{tipoLabel[t]}</option>)}
                </select>
              </Field>
              <Field label="Orçamento (€)"><input type="number" className={inputCls} value={form.orcamento} onChange={e => setForm(f => ({ ...f, orcamento: e.target.value }))} /></Field>
              <Field label="Zona preferida"><input className={inputCls} value={form.zona_preferida} onChange={e => setForm(f => ({ ...f, zona_preferida: e.target.value }))} /></Field>
              <Field label="Origem">
                <select className={selectCls} value={form.origem} onChange={e => setForm(f => ({ ...f, origem: e.target.value }))}>
                  {ORIGENS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Notas"><textarea className={inputCls} rows={2} value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} /></Field>
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
