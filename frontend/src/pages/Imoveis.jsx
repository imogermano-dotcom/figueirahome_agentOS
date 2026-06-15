import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { supabase } from '../lib/supabase'

const TIPOS = ['apartamento', 'moradia', 'terreno', 'comercial']
const ESTADOS = ['disponivel', 'reservado', 'vendido']
const EMPTY_FORM = { referencia: '', tipo: '', localizacao: '', preco: '', area: '', quartos: '', descricao: '', estado: 'disponivel' }

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"
const selectCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500 transition-colors"

const estadoBadge = {
  disponivel: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  reservado: 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
  vendido: 'bg-zinc-700 text-zinc-500',
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

export default function Imoveis() {
  const [imoveis, setImoveis] = useState([])
  const [loading, setLoading] = useState(true)
  const [estadoFiltro, setEstadoFiltro] = useState('')
  const [localFiltro, setLocalFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const fileRef = useRef()

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (estadoFiltro) params.set('estado', estadoFiltro)
    if (localFiltro) params.set('localizacao', localFiltro)
    try { setImoveis(await api.get(`/api/imoveis?${params}`)) }
    catch { setError('Erro ao carregar imóveis.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [estadoFiltro, localFiltro])

  function openNew() { setForm(EMPTY_FORM); setModal('new') }
  function openEdit(im) {
    setForm({ referencia: im.referencia||'', tipo: im.tipo||'', localizacao: im.localizacao||'',
      preco: im.preco??'', area: im.area??'', quartos: im.quartos??'', descricao: im.descricao||'', estado: im.estado||'disponivel' })
    setModal(im)
  }

  async function handleSave(e) {
    e.preventDefault(); setSaving(true)
    const body = { ...form,
      preco: form.preco !== '' ? Number(form.preco) : undefined,
      area: form.area !== '' ? Number(form.area) : undefined,
      quartos: form.quartos !== '' ? Number(form.quartos) : undefined,
    }
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k])
    try {
      modal === 'new' ? await api.post('/api/imoveis', body) : await api.put(`/api/imoveis/${modal.id}`, body)
      setModal(null); load()
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  async function handleDelete(id) {
    if (!confirm('Apagar este imóvel?')) return
    try { await api.delete(`/api/imoveis/${id}`); load() }
    catch (err) { setError(err.message) }
  }

  async function handleImport(e) {
    const file = e.target.files[0]; if (!file) return
    setImporting(true); setError('')
    const { data: s } = await supabase.auth.getSession()
    const token = s?.session?.access_token
    const base = import.meta.env.VITE_API_BASE_URL
    const fd = new FormData(); fd.append('file', file)
    try {
      const res = await fetch(`${base}/api/imoveis/import`, { method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd })
      if (!res.ok) throw new Error((await res.json()).detail || 'Erro')
      const r = await res.json(); alert(`${r.importados} imóveis importados.`); load()
    } catch (err) { setError(err.message) }
    setImporting(false); if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Imóveis</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{imoveis.length} imóve{imoveis.length !== 1 ? 'is' : 'l'}</p>
        </div>
        <div className="flex gap-2">
          <label className={`cursor-pointer border border-zinc-700 hover:border-zinc-500 text-zinc-400 hover:text-zinc-200 text-sm font-medium px-4 py-2 rounded-lg transition-all ${importing ? 'opacity-50 pointer-events-none' : ''}`}>
            {importing ? 'A importar…' : 'Importar CSV'}
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleImport} />
          </label>
          <button onClick={openNew} className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20">
            + Novo imóvel
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="flex gap-3 mb-4">
        <input placeholder="Filtrar por localização…" value={localFiltro} onChange={e => setLocalFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:border-blue-500 transition-colors" />
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
              <th className="px-4 py-3">Referência</th>
              <th className="px-4 py-3">Tipo</th>
              <th className="px-4 py-3">Localização</th>
              <th className="px-4 py-3">Preço</th>
              <th className="px-4 py-3">Quartos</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Fonte</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && imoveis.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">Sem imóveis.</td></tr>}
            {imoveis.map(im => (
              <tr key={im.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">{im.referencia || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.tipo || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.localizacao || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.preco ? `${Number(im.preco).toLocaleString('pt-PT')} €` : '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.quartos ?? '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${estadoBadge[im.estado] || 'bg-zinc-700 text-zinc-400'}`}>{im.estado}</span>
                </td>
                <td className="px-4 py-3 text-zinc-600 text-xs">{im.fonte}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => openEdit(im)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Editar</button>
                    <button onClick={() => handleDelete(im.id)} className="text-xs text-red-500 hover:text-red-400 transition-colors">Apagar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'new' ? 'Novo imóvel' : 'Editar imóvel'} onClose={() => setModal(null)}>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Referência"><input className={inputCls} value={form.referencia} onChange={e => setForm(f => ({ ...f, referencia: e.target.value }))} /></Field>
              <Field label="Tipo">
                <select className={selectCls} value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))}>
                  <option value="">— seleccionar —</option>
                  {TIPOS.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
                </select>
              </Field>
              <Field label="Localização"><input className={inputCls} value={form.localizacao} onChange={e => setForm(f => ({ ...f, localizacao: e.target.value }))} /></Field>
              <Field label="Preço (€)"><input type="number" className={inputCls} value={form.preco} onChange={e => setForm(f => ({ ...f, preco: e.target.value }))} /></Field>
              <Field label="Área (m²)"><input type="number" className={inputCls} value={form.area} onChange={e => setForm(f => ({ ...f, area: e.target.value }))} /></Field>
              <Field label="Quartos"><input type="number" className={inputCls} value={form.quartos} onChange={e => setForm(f => ({ ...f, quartos: e.target.value }))} /></Field>
              <Field label="Estado">
                <select className={selectCls} value={form.estado} onChange={e => setForm(f => ({ ...f, estado: e.target.value }))}>
                  {ESTADOS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Descrição"><textarea className={inputCls} rows={3} value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} /></Field>
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
