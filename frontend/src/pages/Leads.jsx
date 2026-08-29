import { useEffect, useState } from 'react'
import { api } from '../lib/api'

// Vocabulário de `leads` (migration 0021), alargado com as etapas comerciais que
// vinham do painel antigo. `guards._ESTADOS_LEAD_ABERTA` depende dos três
// primeiros — não renomear sem olhar para lá.
const ESTADOS = ['nova', 'contactada', 'sem_resposta', 'qualificada', 'visita', 'proposta', 'fechada', 'perdida', 'sem_interesse', 'engano']

// `sem_resposta` não é cinzento como os outros desfechos: a lead continua aberta
// (`guards._ESTADOS_LEAD_ABERTA`) e se responder tarde volta para a Matilde.
const estadoBadge = {
  nova: 'bg-blue-500/15 text-blue-400 border border-blue-500/20',
  contactada: 'bg-amber-500/15 text-amber-400 border border-amber-500/20',
  sem_resposta: 'bg-amber-500/10 text-amber-500/70 border border-amber-500/15',
  qualificada: 'bg-teal-500/15 text-teal-400 border border-teal-500/20',
  visita: 'bg-violet-500/15 text-violet-400 border border-violet-500/20',
  proposta: 'bg-orange-500/15 text-orange-400 border border-orange-500/20',
  fechada: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  perdida: 'bg-zinc-700 text-zinc-500',
  sem_interesse: 'bg-zinc-700 text-zinc-500',
  engano: 'bg-zinc-700 text-zinc-500',
}

const ORIGENS = ['meta', 'assistente', 'voz', 'landing', 'manual']

// Consentimento de canal, do formulário da Meta. A recusa é só do WhatsApp:
// quem preencheu o formulário continua contactável por telefone até dizer o
// contrário. Sem este distintivo, estas leads não têm caminho nenhum — o
// automático está fechado (filtro no n8n) e ninguém sabe que existem.
//
// Reconhecido pelo prefixo, não por igualdade a um literal: entre 18 e 20 de
// Agosto o valor passou de 'sim,_aceito_receber_informações_pelo_whatsapp' para
// 'SIM'. A versão que comparava com a frase inteira marcou as 152 leads como
// recusa durante dois dias — e a mesma armadilha existe no filtro do n8n.
//
// Opt-in: só conta como consentimento o que começa por "sim". Sem remoção de
// acentos porque nenhum dos valores os tem no início, e "não" nunca começa por
// "sim" — a regra funciona para 'SIM', 'Sim', 'sim,_aceito…' e falha em segurança
// para qualquer coisa que a Meta invente a seguir.
//
// `null` = não respondeu (sem distintivo), `false` = recusou, `true` = aceitou.
function aceitaWhatsapp(lead) {
  const v = lead.ficha?.aceita_whatsapp
  if (typeof v !== 'string' || !v.trim()) return null
  return v.trim().toLowerCase().startsWith('sim')
}

const recusaWhatsapp = lead => aceitaWhatsapp(lead) === false

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
  const [origemFiltro, setOrigemFiltro] = useState('')
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({ estado: 'nova', notas: '', responsavel: '', contacto_humano: false })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (estadoFiltro) params.set('estado', estadoFiltro)
    if (origemFiltro) params.set('origem', origemFiltro)
    try { setLeads(await api.get(`/api/leads?${params}`)) }
    catch { setError('Erro ao carregar leads.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [estadoFiltro, origemFiltro])

  // `contacto_humano` é booleano e a coluna é um carimbo: o modal lê o carimbo
  // e manda a intenção. Quem decide a hora é o servidor (`api/leads.py`).
  function openEdit(lead) {
    setForm({
      estado: lead.estado || 'nova',
      notas: lead.notas || '',
      responsavel: lead.responsavel || '',
      contacto_humano: !!lead.contacto_humano_em,
    })
    setModal(lead)
  }

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
          {ESTADOS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>)}
        </select>
        <select value={origemFiltro} onChange={e => setOrigemFiltro(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors">
          <option value="">Todas as origens</option>
          {ORIGENS.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
        </select>
      </div>

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-zinc-500 text-xs uppercase tracking-widest">
              <th className="px-4 py-3">Cliente</th>
              <th className="px-4 py-3">Telefone</th>
              <th className="px-4 py-3">Origem</th>
              <th className="px-4 py-3">Imóvel</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Notas</th>
              <th className="px-4 py-3">Data</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">A carregar…</td></tr>}
            {!loading && leads.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">Sem leads.</td></tr>}
            {leads.map(lead => (
              <tr key={lead.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 font-medium text-zinc-100">
                  {lead.nome_display || '—'}
                  {recusaWhatsapp(lead) && (
                    <span title="Recusou contacto por WhatsApp no formulário. Contacto telefónico continua autorizado."
                      className="ml-2 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/20">
                      só telefone
                    </span>
                  )}
                  {lead.contacto_humano_em && (
                    <span title={`Contactada por ${lead.responsavel || 'uma consultora'} a ${formatDate(lead.contacto_humano_em)}. Os envios automáticos estão travados.`}
                      className="ml-2 px-2 py-0.5 rounded-full text-xs font-medium bg-violet-500/15 text-violet-400 border border-violet-500/20">
                      consultora
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-zinc-400">{lead.telefone_display || '—'}</td>
                <td className="px-4 py-3 text-zinc-500 text-xs">{lead.origem || '—'}</td>
                <td className="px-4 py-3 text-zinc-400 text-xs">{lead.imovel_ref || '—'}</td>
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
                {ESTADOS.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Notas</label>
              <textarea className={inputCls} rows={3} value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} />
            </div>

            {/* Trava os envios que NÓS iniciamos — o template do fluxo 02 e o
                follow-up do 03. Não trava a Matilde a responder a quem escreve:
                a conversa é dela, e calá-la punha o cliente a falar para o vazio. */}
            <div className="rounded-xl border border-white/5 bg-zinc-800/40 p-4 space-y-3">
              <label className="flex items-start gap-3 cursor-pointer">
                <input type="checkbox" checked={form.contacto_humano}
                  onChange={e => setForm(f => ({ ...f, contacto_humano: e.target.checked }))}
                  className="mt-0.5 h-4 w-4 shrink-0 rounded border-zinc-600 bg-zinc-800 text-violet-500 focus:ring-violet-500 focus:ring-offset-0 accent-violet-500" />
                <span className="text-sm text-zinc-200">
                  Contactada por uma consultora
                  <span className="block text-xs text-zinc-500 mt-0.5">
                    A Matilde deixa de lhe enviar mensagens. Continua a responder se a pessoa escrever.
                  </span>
                </span>
              </label>
              {form.contacto_humano && (
                <input className={inputCls} placeholder="Quem falou com ela"
                  value={form.responsavel} onChange={e => setForm(f => ({ ...f, responsavel: e.target.value }))} />
              )}
              {modal.contacto_humano_em && (
                <p className="text-xs text-zinc-500">Marcada a {formatDate(modal.contacto_humano_em)}.</p>
              )}
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
