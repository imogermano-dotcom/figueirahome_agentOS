import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import AgenteMetricas from '../components/AgenteMetricas'
import AgenteConversas from '../components/AgenteConversas'

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"

// Título, subtítulo e aviso por assistente. A página em si é genérica —
// persona/instruções/activo são os mesmos campos para todos.
export const META = {
  a1_vendedor: {
    titulo: 'A1 — Assistente Vendedor',
    subtitulo: 'Qualifica compradores e arrendatários, mostra imóveis e marca visitas.',
    icon: '🏠',
    placeholderPersona: 'Ex: Assistente comercial da Figueirahome, tom profissional e caloroso…',
    placeholderInstrucoes: 'Ex: Foca-te na zona da Figueira da Foz. Menciona o portefólio de moradias…',
  },
  a2_geral: {
    titulo: 'A2 — Atendimento Geral',
    subtitulo: 'Recepcionista virtual: horários, morada, serviços, e encaminhamento.',
    icon: '📞',
    placeholderPersona: 'Ex: Recepcionista virtual da Figueirahome, cordial e breve…',
    placeholderInstrucoes: 'Horários, morada, serviços, parceiros de crédito. É daqui que o A2 responde — mantém actualizado.',
  },
  voz: {
    titulo: 'Agente de Voz',
    subtitulo: 'Atendimento telefónico automático.',
    icon: '☎',
    aviso: (
      <>
        <span className="font-medium">Credenciais Telnyx em falta</span> — chamadas bloqueadas até configurar
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_API_KEY</code>,
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_PUBLIC_KEY</code> e
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_PHONE_NUMBER</code>.
      </>
    ),
    placeholderPersona: 'Ex: Assistente simpático e profissional da agência Figueirahome…',
    placeholderInstrucoes: 'Ex: Confirma sempre os dados em voz alta antes de terminar a chamada…',
  },
  broker: {
    titulo: 'Assistente Broker (interno)',
    subtitulo: 'Uso exclusivo do corretor — acesso de leitura à base de dados.',
    icon: '🔒',
    placeholderPersona: 'Ex: Assistente directo e objectivo, respostas estruturadas…',
    placeholderInstrucoes: 'Ex: Apresenta sempre os valores em euros e ordena por data mais recente…',
  },
}

const FALLBACK = { titulo: 'Assistente', subtitulo: '', icon: '🤖' }

const ABAS = [
  { id: 'config', label: 'Configuração' },
  { id: 'metricas', label: 'Métricas' },
  { id: 'conversas', label: 'Conversas' },
]

export default function AgenteConfig() {
  const { agente } = useParams()
  const meta = META[agente] || FALLBACK

  const [aba, setAba] = useState('config')
  const [form, setForm] = useState({ persona: '', instrucoes: '', ativo: true })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError(''); setSuccess(false)
    api.get(`/api/config/${agente}`)
      .then(data => setForm({ persona: data.persona||'', instrucoes: data.instrucoes||'', ativo: data.ativo??true }))
      .catch(() => setError('Erro ao carregar configuração.'))
      .finally(() => setLoading(false))
  }, [agente])

  async function handleSave(e) {
    e.preventDefault(); setSaving(true); setSuccess(false); setError('')
    try {
      await api.put(`/api/config/${agente}`, form)
      setSuccess(true); setTimeout(() => setSuccess(false), 3000)
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  return (
    <div className={aba === 'config' ? 'max-w-2xl' : 'max-w-5xl'}>
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-white">{meta.icon} {meta.titulo}</h1>
        <p className="text-zinc-500 text-sm mt-1">{meta.subtitulo}</p>
      </div>

      <div className="flex gap-1 mb-6 border-b border-white/5">
        {ABAS.map(a => (
          <button key={a.id} onClick={() => setAba(a.id)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              aba === a.id ? 'text-white border-blue-500'
                           : 'text-zinc-500 hover:text-zinc-300 border-transparent'}`}>
            {a.label}
          </button>
        ))}
      </div>

      {aba === 'metricas' && <AgenteMetricas agente={agente} />}
      {aba === 'conversas' && <AgenteConversas agente={agente} />}

      {aba === 'config' && meta.aviso && (
        <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-400">
          {meta.aviso}
        </div>
      )}

      {aba !== 'config' ? null : loading ? (
        <p className="text-zinc-600 text-sm">A carregar…</p>
      ) : (
        <form onSubmit={handleSave} className="bg-zinc-900 border border-white/5 rounded-2xl p-6 space-y-5">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Persona</label>
            <p className="text-xs text-zinc-600 mb-2">Tom, nome e estilo do assistente.</p>
            <textarea className={inputCls} rows={3} value={form.persona}
              onChange={e => setForm(f => ({ ...f, persona: e.target.value }))}
              placeholder={meta.placeholderPersona} />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Instruções</label>
            <p className="text-xs text-zinc-600 mb-2">Directivas acrescentadas ao prompt base.</p>
            <textarea className={inputCls} rows={7} value={form.instrucoes}
              onChange={e => setForm(f => ({ ...f, instrucoes: e.target.value }))}
              placeholder={meta.placeholderInstrucoes} />
          </div>

          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setForm(f => ({ ...f, ativo: !f.ativo }))}
              className={`relative w-10 h-5 rounded-full transition-colors ${form.ativo ? 'bg-blue-600' : 'bg-zinc-700'}`}>
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow ${form.ativo ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
            <span className="text-sm text-zinc-400">
              Assistente activo
              {!form.ativo && <span className="text-amber-500 ml-2">— responde com mensagem de handoff</span>}
            </span>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}
          {success && <p className="text-emerald-400 text-sm">Configuração guardada.</p>}

          <div className="flex justify-end pt-1">
            <button type="submit" disabled={saving}
              className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-6 py-2 rounded-lg disabled:opacity-50 transition-all shadow-lg shadow-blue-500/20">
              {saving ? 'A guardar…' : 'Guardar configuração'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
