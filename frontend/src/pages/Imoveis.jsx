import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { supabase } from '../lib/supabase'

const DISPONIBILIDADES = ['Disponível', 'Em Prospecção', 'Por validar', 'Retirado']
const TAREFA_ESTADOS = ['pendente', 'em_curso', 'concluida', 'cancelada']
const EMPTY_IMOVEL = {
  imovel_ref: '', natureza: '', disponibilidade: 'Disponível', estado: '',
  concelho: '', freguesia: '', venda_preco: '', arrendamento_preco: '',
  area_util: '', quartos: '', descricao: '',
}
const EMPTY_TAREFA = { titulo: '', descricao: '', imovel_ref: '', estado: 'pendente', prazo: '', responsavel: '' }

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"
const selectCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-blue-500 transition-colors"

const disponibilidadeBadge = {
  'Disponível': 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  'Em Prospecção': 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
  'Por validar': 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
  'Retirado': 'bg-zinc-700 text-zinc-500',
}

const tarefaBadge = {
  pendente: 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
  em_curso: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
  concluida: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  cancelada: 'bg-zinc-700 text-zinc-500',
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

function fmtEuro(v) {
  return v ? `${Number(v).toLocaleString('pt-PT')} €` : '—'
}

function PortfolioTab() {
  const [imoveis, setImoveis] = useState([])
  const [loading, setLoading] = useState(true)
  const [dispFiltro, setDispFiltro] = useState('')
  const [concelhoFiltro, setConcelhoFiltro] = useState('')
  const [refFiltro, setRefFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY_IMOVEL)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [importing, setImporting] = useState(false)
  const fileRef = useRef()

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (dispFiltro) params.set('disponibilidade', dispFiltro)
    if (concelhoFiltro) params.set('concelho', concelhoFiltro)
    if (refFiltro) params.set('imovel_ref', refFiltro)
    try { setImoveis(await api.get(`/api/imoveis?${params}`)) }
    catch { setError('Erro ao carregar imóveis.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [dispFiltro, concelhoFiltro, refFiltro])

  function openNew() { setForm(EMPTY_IMOVEL); setModal('new') }
  function openEdit(im) {
    setForm({
      imovel_ref: im.imovel_ref || '', natureza: im.natureza || '', disponibilidade: im.disponibilidade || 'Disponível',
      estado: im.estado || '', concelho: im.concelho || '', freguesia: im.freguesia || '',
      venda_preco: im.venda_preco ?? '', arrendamento_preco: im.arrendamento_preco ?? '',
      area_util: im.area_util ?? '', quartos: im.quartos ?? '', descricao: im.descricao || '',
    })
    setModal(im)
  }

  async function handleSave(e) {
    e.preventDefault(); setSaving(true)
    const body = { ...form,
      venda_preco: form.venda_preco !== '' ? Number(form.venda_preco) : undefined,
      arrendamento_preco: form.arrendamento_preco !== '' ? Number(form.arrendamento_preco) : undefined,
      area_util: form.area_util !== '' ? Number(form.area_util) : undefined,
      quartos: form.quartos !== '' ? Number(form.quartos) : undefined,
    }
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k])
    try {
      modal === 'new' ? await api.post('/api/imoveis', body) : await api.put(`/api/imoveis/${encodeURIComponent(modal.imovel_ref)}`, body)
      setModal(null); load()
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  async function handleDelete(ref) {
    if (!confirm('Apagar este imóvel?')) return
    try { await api.delete(`/api/imoveis/${encodeURIComponent(ref)}`); load() }
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
        <p className="text-zinc-500 text-sm">{imoveis.length} imóve{imoveis.length !== 1 ? 'is' : 'l'}</p>
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
        <input placeholder="Filtrar por referência…" value={refFiltro} onChange={e => setRefFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-lg px-3 py-2 text-sm w-48 focus:outline-none focus:border-blue-500 transition-colors" />
        <input placeholder="Filtrar por concelho…" value={concelhoFiltro} onChange={e => setConcelhoFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:border-blue-500 transition-colors" />
        <select value={dispFiltro} onChange={e => setDispFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors">
          <option value="">Todas as disponibilidades</option>
          {DISPONIBILIDADES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-zinc-500 text-xs uppercase tracking-widest">
              <th className="px-4 py-3">Referência</th>
              <th className="px-4 py-3">Natureza</th>
              <th className="px-4 py-3">Concelho</th>
              <th className="px-4 py-3">Venda</th>
              <th className="px-4 py-3">Arrendamento</th>
              <th className="px-4 py-3">Quartos</th>
              <th className="px-4 py-3">Disponibilidade</th>
              <th className="px-4 py-3">Fonte</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={9} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && imoveis.length === 0 && <tr><td colSpan={9} className="px-4 py-8 text-center text-zinc-600">Sem imóveis.</td></tr>}
            {imoveis.map(im => (
              <tr key={im.imovel_ref} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">{im.imovel_ref}</td>
                <td className="px-4 py-3 text-zinc-400">{im.natureza || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.concelho || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{fmtEuro(im.venda_preco)}</td>
                <td className="px-4 py-3 text-zinc-400">{im.arrendamento_preco ? `${fmtEuro(im.arrendamento_preco)}/mês` : '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{im.quartos ?? '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${disponibilidadeBadge[im.disponibilidade] || 'bg-zinc-700 text-zinc-400'}`}>{im.disponibilidade || '—'}</span>
                </td>
                <td className="px-4 py-3 text-zinc-600 text-xs">{im.fonte}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => openEdit(im)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Editar</button>
                    <button onClick={() => handleDelete(im.imovel_ref)} className="text-xs text-red-500 hover:text-red-400 transition-colors">Apagar</button>
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
              <Field label="Referência">
                <input className={inputCls} value={form.imovel_ref} disabled={modal !== 'new'}
                  onChange={e => setForm(f => ({ ...f, imovel_ref: e.target.value }))} />
              </Field>
              <Field label="Natureza"><input className={inputCls} value={form.natureza} onChange={e => setForm(f => ({ ...f, natureza: e.target.value }))} /></Field>
              <Field label="Concelho"><input className={inputCls} value={form.concelho} onChange={e => setForm(f => ({ ...f, concelho: e.target.value }))} /></Field>
              <Field label="Freguesia"><input className={inputCls} value={form.freguesia} onChange={e => setForm(f => ({ ...f, freguesia: e.target.value }))} /></Field>
              <Field label="Preço venda (€)"><input type="number" className={inputCls} value={form.venda_preco} onChange={e => setForm(f => ({ ...f, venda_preco: e.target.value }))} /></Field>
              <Field label="Preço arrendamento (€)"><input type="number" className={inputCls} value={form.arrendamento_preco} onChange={e => setForm(f => ({ ...f, arrendamento_preco: e.target.value }))} /></Field>
              <Field label="Área útil (m²)"><input type="number" className={inputCls} value={form.area_util} onChange={e => setForm(f => ({ ...f, area_util: e.target.value }))} /></Field>
              <Field label="Quartos"><input type="number" className={inputCls} value={form.quartos} onChange={e => setForm(f => ({ ...f, quartos: e.target.value }))} /></Field>
              <Field label="Disponibilidade">
                <select className={selectCls} value={form.disponibilidade} onChange={e => setForm(f => ({ ...f, disponibilidade: e.target.value }))}>
                  {DISPONIBILIDADES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Condição"><input className={inputCls} value={form.estado} onChange={e => setForm(f => ({ ...f, estado: e.target.value }))} placeholder="Novo, Usado, ..." /></Field>
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

function TarefasTab() {
  const [tarefas, setTarefas] = useState([])
  const [loading, setLoading] = useState(true)
  const [estadoFiltro, setEstadoFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState(EMPTY_TAREFA)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (estadoFiltro) params.set('estado', estadoFiltro)
    try { setTarefas(await api.get(`/api/tarefas?${params}`)) }
    catch { setError('Erro ao carregar tarefas.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [estadoFiltro])

  function openNew() { setForm(EMPTY_TAREFA); setModal('new') }
  function openEdit(t) {
    setForm({
      titulo: t.titulo || '', descricao: t.descricao || '', imovel_ref: t.imovel_ref || '',
      estado: t.estado || 'pendente', prazo: t.prazo || '', responsavel: t.responsavel || '',
    })
    setModal(t)
  }

  async function handleSave(e) {
    e.preventDefault(); setSaving(true)
    const body = { ...form }
    if (!body.prazo) delete body.prazo
    if (!body.imovel_ref) delete body.imovel_ref
    try {
      modal === 'new' ? await api.post('/api/tarefas', body) : await api.put(`/api/tarefas/${modal.id}`, body)
      setModal(null); load()
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  async function handleDelete(id) {
    if (!confirm('Apagar esta tarefa?')) return
    try { await api.delete(`/api/tarefas/${id}`); load() }
    catch (err) { setError(err.message) }
  }

  async function handleDeleteAll() {
    if (!confirm(`Apagar TODAS as ${tarefas.length} tarefas? Não pode ser desfeito.`)) return
    try { await api.delete('/api/tarefas'); load() }
    catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <p className="text-zinc-500 text-sm">{tarefas.length} tarefa{tarefas.length !== 1 ? 's' : ''}</p>
        <div className="flex gap-3">
          {tarefas.length > 0 && (
            <button onClick={handleDeleteAll} className="text-sm text-red-500 hover:text-red-400 transition-colors px-4 py-2">
              Apagar todas
            </button>
          )}
          <button onClick={openNew} className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20">
            + Nova tarefa
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="flex gap-3 mb-4">
        <select value={estadoFiltro} onChange={e => setEstadoFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors">
          <option value="">Todos os estados</option>
          {TAREFA_ESTADOS.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
      </div>

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-zinc-500 text-xs uppercase tracking-widest">
              <th className="px-4 py-3">Título</th>
              <th className="px-4 py-3">Imóvel</th>
              <th className="px-4 py-3">Responsável</th>
              <th className="px-4 py-3">Prazo</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && tarefas.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600">Sem tarefas.</td></tr>}
            {tarefas.map(t => (
              <tr key={t.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">{t.titulo}</td>
                <td className="px-4 py-3 text-zinc-400">{t.imovel_ref || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{t.responsavel || '—'}</td>
                <td className="px-4 py-3 text-zinc-400">{t.prazo || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${tarefaBadge[t.estado] || 'bg-zinc-700 text-zinc-400'}`}>{t.estado.replace('_', ' ')}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-3 justify-end">
                    <button onClick={() => openEdit(t)} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Editar</button>
                    <button onClick={() => handleDelete(t.id)} className="text-xs text-red-500 hover:text-red-400 transition-colors">Apagar</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title={modal === 'new' ? 'Nova tarefa' : 'Editar tarefa'} onClose={() => setModal(null)}>
          <form onSubmit={handleSave} className="space-y-4">
            <Field label="Título"><input required className={inputCls} value={form.titulo} onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))} /></Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Imóvel (referência)"><input className={inputCls} value={form.imovel_ref} onChange={e => setForm(f => ({ ...f, imovel_ref: e.target.value }))} /></Field>
              <Field label="Responsável"><input className={inputCls} value={form.responsavel} onChange={e => setForm(f => ({ ...f, responsavel: e.target.value }))} /></Field>
              <Field label="Prazo"><input type="date" className={inputCls} value={form.prazo} onChange={e => setForm(f => ({ ...f, prazo: e.target.value }))} /></Field>
              <Field label="Estado">
                <select className={selectCls} value={form.estado} onChange={e => setForm(f => ({ ...f, estado: e.target.value }))}>
                  {TAREFA_ESTADOS.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
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

function formatDataHora(iso) {
  return new Date(iso).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })
}

function descreverAlteracao(item) {
  if (item.tipo === 'criado') return `${item.imovel_ref} — criado (via eGO)`
  if (item.tipo === 'atualizado') return `${item.imovel_ref} — actualizado (via eGO)`
  if (item.tipo === 'nao_publicado') return `${item.imovel_ref} — deixou de estar publicado, tarefa criada`
  if (item.tipo === 'corrigido_crm') {
    const campos = Object.entries(item.alteracoes || {})
      .map(([campo, { de, para }]) => `${campo}: ${de ?? '—'} → ${para}`)
      .join(', ')
    return `${item.imovel_ref} — ${campos} (corrigido via CRM)`
  }
  return `${item.imovel_ref} — ${item.tipo}`
}

function SincronizacaoTab() {
  const [syncing, setSyncing] = useState(false)
  const [log, setLog] = useState([])
  const [error, setError] = useState('')

  async function carregarLog() {
    try { setLog(await api.get('/api/imoveis/sync/log?limit=20')) }
    catch (err) { setError(err.message) }
  }

  useEffect(() => { carregarLog() }, [])

  async function handleSync() {
    setSyncing(true); setError('')
    try { await api.post('/api/imoveis/sync/egorealestate'); await carregarLog() }
    catch (err) { setError(err.message) }
    setSyncing(false)
  }

  async function handleDeleteLog() {
    if (!confirm('Apagar TODO o histórico de sincronizações? Não pode ser desfeito.')) return
    try { await api.delete('/api/imoveis/sync/log'); await carregarLog() }
    catch (err) { setError(err.message) }
  }

  const ultima = log[0]

  return (
    <div className="bg-zinc-900 border border-white/5 rounded-2xl p-6 max-w-2xl">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold text-white">eGO Real Estate</h2>
        {log.length > 0 && (
          <button onClick={handleDeleteLog} className="text-xs text-red-500 hover:text-red-400 transition-colors">
            Apagar histórico
          </button>
        )}
      </div>
      <p className="text-zinc-500 text-sm mb-4">Sincroniza o portefólio com o CRM. Corre automaticamente todos os dias; podes também disparar manualmente.</p>
      <button onClick={handleSync} disabled={syncing}
        className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50">
        {syncing ? 'A sincronizar…' : 'Sincronizar agora'}
      </button>

      {error && <p className="text-red-400 text-sm mt-4">{error}</p>}

      {ultima && (
        <>
          <p className="text-zinc-500 text-xs mt-5 mb-2">Última execução: {formatDataHora(ultima.executado_em)}</p>
          <div className="grid grid-cols-5 gap-3 text-center">
            <div>
              <p className="text-2xl font-bold text-emerald-400">{ultima.resumo.criados}</p>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">Criados</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-blue-400">{ultima.resumo.atualizados}</p>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">Actualizados</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-teal-400">{ultima.resumo.corrigidos}</p>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">Corrigidos</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-amber-400">{ultima.resumo.nao_publicados}</p>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">Não publicados</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-red-400">{ultima.resumo.erros}</p>
              <p className="text-xs text-zinc-500 uppercase tracking-wide">Erros</p>
            </div>
          </div>

          {ultima.detalhes?.length > 0 && (
            <div className="mt-4 max-h-64 overflow-y-auto bg-zinc-950/50 rounded-lg p-3 space-y-1">
              {ultima.detalhes.map((item, i) => (
                <p key={i} className="text-xs text-zinc-400">{descreverAlteracao(item)}</p>
              ))}
            </div>
          )}

          {log.length > 1 && (
            <div className="mt-6">
              <p className="text-zinc-500 text-xs uppercase tracking-wide mb-2">Execuções anteriores</p>
              <div className="space-y-1">
                {log.slice(1).map(exec => (
                  <p key={exec.id} className="text-xs text-zinc-500">
                    {formatDataHora(exec.executado_em)} — {exec.resumo.criados} criados, {exec.resumo.atualizados} actualizados, {exec.resumo.corrigidos} corrigidos, {exec.resumo.nao_publicados} não publicados, {exec.resumo.erros} erros
                  </p>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const TABS = [
  { key: 'portfolio', label: 'Portfólio' },
  { key: 'tarefas', label: 'Tarefas' },
  { key: 'sync', label: 'Sincronização' },
]

export default function Imoveis() {
  const [aba, setAba] = useState('portfolio')

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Imóveis</h1>
        <p className="text-zinc-500 text-sm mt-0.5">Portefólio, tarefas e sincronização</p>
      </div>

      <div className="flex gap-1 mb-6 border-b border-white/5">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setAba(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              aba === t.key ? 'border-blue-500 text-white' : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {aba === 'portfolio' && <PortfolioTab />}
      {aba === 'tarefas' && <TarefasTab />}
      {aba === 'sync' && <SincronizacaoTab />}
    </div>
  )
}
