import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const usd = n => `$${(n ?? 0).toFixed(4)}`
const VERMELHO = '#d03b3b'

const dataCurta = s => new Date(s).toLocaleString('pt-PT', {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
})

function Transcricao({ id, onFechar }) {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get(`/api/agentes/conversas/${id}`).then(setD).catch(() => setError('Erro ao carregar.'))
  }, [id])

  return (
    <div className="bg-zinc-900 border border-white/5 rounded-2xl p-5">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Transcrição</h3>
          {d && <p className="text-xs text-zinc-600 mt-0.5">
            {d.canal} · {d.participante} · {d.turnos?.length || 0} turnos
          </p>}
        </div>
        <button onClick={onFechar} className="text-xs text-zinc-500 hover:text-zinc-300 shrink-0">
          Fechar
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}
      {!d && !error && <p className="text-zinc-600 text-sm">A carregar…</p>}

      {d && (
        <div className="space-y-3 max-h-[32rem] overflow-y-auto">
          {(d.mensagens || []).map((m, i) => {
            // Os turnos são gravados por resposta do assistente, pela mesma
            // ordem — o i-ésimo assistente casa com o i-ésimo turno.
            const idx = (d.mensagens || []).slice(0, i + 1)
              .filter(x => x.role === 'assistant').length - 1
            const t = m.role === 'assistant' ? d.turnos?.[idx] : null
            return (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] ${m.role === 'user' ? '' : 'w-full'}`}>
                  <div className={`px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                    m.role === 'user'
                      ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-br-sm'
                      : 'bg-zinc-800 border border-white/5 text-zinc-200 rounded-bl-sm'
                  }`}>
                    {m.content}
                  </div>
                  {t && (
                    <p className="text-xs text-zinc-600 mt-1 px-1">
                      {usd(t.custo_usd)} · {t.latencia_ms}ms · {t.iteracoes} iter
                      {t.tools_usadas?.length > 0 && ` · ${t.tools_usadas.join(', ')}`}
                      {t.erro && <span style={{ color: VERMELHO }}> · erro</span>}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function AgenteConversas({ agente }) {
  const [linhas, setLinhas] = useState(null)
  const [aberta, setAberta] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setLinhas(null); setAberta(null); setError('')
    api.get(`/api/agentes/conversas?agente=${agente}&limite=25`)
      .then(setLinhas)
      .catch(() => setError('Erro ao carregar conversas.'))
  }, [agente])

  if (error) return <p className="text-red-400 text-sm">{error}</p>
  if (!linhas) return <p className="text-zinc-600 text-sm">A carregar…</p>
  if (!linhas.length) {
    return <p className="text-zinc-600 text-sm">Ainda sem conversas para este assistente.</p>
  }

  return (
    <div className="space-y-4">
      {aberta && <Transcricao id={aberta} onFechar={() => setAberta(null)} />}

      <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-hidden">
        {linhas.map(c => (
          <button
            key={c.id}
            onClick={() => setAberta(c.id === aberta ? null : c.id)}
            className={`w-full text-left px-5 py-3 border-b border-white/5 last:border-0 transition-colors ${
              c.id === aberta ? 'bg-white/5' : 'hover:bg-white/5'}`}
          >
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-sm text-zinc-200 truncate">
                {c.primeira_mensagem || <span className="text-zinc-600">(sem mensagem)</span>}
              </span>
              <span className="text-xs text-zinc-400 tabular-nums shrink-0">
                {c.turnos ? usd(c.custo_usd) : <span className="text-zinc-600">sem dados</span>}
              </span>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-zinc-600">
              <span>{dataCurta(c.atualizado_em)}</span>
              <span>{c.canal}</span>
              <span>{c.mensagens} mensagens</span>
              {c.tools > 0 && <span>{c.tools} tools</span>}
              {c.erros > 0 && <span style={{ color: VERMELHO }}>{c.erros} erros</span>}
            </div>
          </button>
        ))}
      </div>

      <p className="text-xs text-zinc-600">
        Conversas anteriores à instrumentação aparecem sem custo — os dados só
        existem a partir do momento em que o registo foi activado.
      </p>
    </div>
  )
}
