import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const inputCls = "w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-blue-500 transition-colors"

export default function Agente1() {
  const [form, setForm] = useState({ persona: '', instrucoes: '', ativo: true })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/api/config/voz')
      .then(data => setForm({ persona: data.persona||'', instrucoes: data.instrucoes||'', ativo: data.ativo??true }))
      .catch(() => setError('Erro ao carregar configuração.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e) {
    e.preventDefault(); setSaving(true); setSuccess(false); setError('')
    try {
      await api.put('/api/config/voz', form)
      setSuccess(true); setTimeout(() => setSuccess(false), 3000)
    } catch (err) { setError(err.message) }
    setSaving(false)
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Agente de Voz</h1>
        <p className="text-zinc-500 text-sm mt-1">Persona e instruções do agente de atendimento (chamadas + WhatsApp).</p>
      </div>

      <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-400">
        <span className="font-medium">Credenciais Telnyx em falta</span> — chamadas bloqueadas até configurar
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_API_KEY</code>,
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_PUBLIC_KEY</code> e
        <code className="mx-1 px-1.5 py-0.5 bg-amber-500/10 rounded text-xs font-mono">TELNYX_PHONE_NUMBER</code>.
        Canal WhatsApp activo.
      </div>

      {loading ? (
        <p className="text-zinc-600 text-sm">A carregar…</p>
      ) : (
        <form onSubmit={handleSave} className="bg-zinc-900 border border-white/5 rounded-2xl p-6 space-y-5">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Persona</label>
            <p className="text-xs text-zinc-600 mb-2">Tom, nome e estilo do agente.</p>
            <textarea className={inputCls} rows={3} value={form.persona}
              onChange={e => setForm(f => ({ ...f, persona: e.target.value }))}
              placeholder="Ex: Assistente simpático e profissional da agência Figueirahome…" />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase tracking-wide">Instruções</label>
            <p className="text-xs text-zinc-600 mb-2">Directivas adicionadas ao prompt base do agente.</p>
            <textarea className={inputCls} rows={5} value={form.instrucoes}
              onChange={e => setForm(f => ({ ...f, instrucoes: e.target.value }))}
              placeholder="Ex: Foca-te sempre na zona de Torres Novas. Menciona o nosso portefólio de moradias…" />
          </div>

          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setForm(f => ({ ...f, ativo: !f.ativo }))}
              className={`relative w-10 h-5 rounded-full transition-colors ${form.ativo ? 'bg-blue-600' : 'bg-zinc-700'}`}>
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow ${form.ativo ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
            <span className="text-sm text-zinc-400">Agente activo</span>
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
