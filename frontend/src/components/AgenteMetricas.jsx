import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Barras from './Barras'

const AZUL = '#3987e5'
const VERDE = '#0ca30c'
const VERMELHO = '#d03b3b'
const AMARELO = '#fab219'

const usd = n => `$${(n ?? 0).toFixed(4)}`
const num = n => (n ?? 0).toLocaleString('pt-PT')
const pct = n => `${((n ?? 0) * 100).toFixed(1)}%`
const ms = n => (n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n ?? 0)}ms`)

const PERIODOS = [
  { dias: 7, label: '7 dias' },
  { dias: 30, label: '30 dias' },
  { dias: 90, label: '90 dias' },
]

function Cartao({ children, className = '' }) {
  return <div className={`bg-zinc-900 border border-white/5 rounded-2xl p-5 ${className}`}>{children}</div>
}

function Kpi({ label, valor, nota, cor }) {
  return (
    <Cartao>
      <p className="text-zinc-500 text-xs uppercase tracking-widest mb-2">{label}</p>
      <p className="text-2xl font-bold" style={{ color: cor || '#fff' }}>{valor}</p>
      {nota && <p className="text-xs text-zinc-600 mt-1">{nota}</p>}
    </Cartao>
  )
}

function Linha({ label, valor, nota }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 border-b border-white/5 last:border-0">
      <span className="text-xs text-zinc-400">{label}</span>
      <span className="text-sm text-zinc-200 tabular-nums shrink-0">
        {valor}
        {nota && <span className="text-xs text-zinc-600 ml-2">{nota}</span>}
      </span>
    </div>
  )
}

export default function AgenteMetricas({ agente }) {
  const [dias, setDias] = useState(30)
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setD(null); setError('')
    api.get(`/api/agentes/metricas?agente=${agente}&dias=${dias}`)
      .then(setD)
      .catch(() => setError('Erro ao carregar métricas.'))
  }, [agente, dias])

  if (error) return <p className="text-red-400 text-sm">{error}</p>
  if (!d) return <p className="text-zinc-600 text-sm">A carregar…</p>

  const { custos: c, volume: v, desempenho: p, eficiencia: e, contexto: ctx } = d
  const semDados = !v?.turnos

  return (
    <div className="space-y-4">
      <div className="flex gap-1.5">
        {PERIODOS.map(o => (
          <button key={o.dias} onClick={() => setDias(o.dias)}
            className={`px-3 py-1 rounded-lg text-xs transition-colors ${
              dias === o.dias ? 'bg-blue-600/30 text-white border border-white/10'
                              : 'text-zinc-500 hover:text-zinc-300 border border-transparent'}`}>
            {o.label}
          </button>
        ))}
      </div>

      {semDados && (
        <div className="p-4 bg-zinc-900 border border-white/5 rounded-xl text-sm text-zinc-500">
          Ainda sem turnos registados neste período. A instrumentação começou a
          gravar a partir do deploy — as conversas anteriores não têm dados de
          custo nem latência.
        </div>
      )}

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <Kpi label="Custo total" valor={usd(c?.total_usd)} cor={AZUL}
             nota={`${num(v?.turnos)} turnos · ${num(v?.conversas)} conversas`} />
        <Kpi label="Custo por conversa"
             valor={usd(v?.conversas ? c?.total_usd / v.conversas : 0)}
             nota={`${usd(c?.media_por_turno)} por turno`} />
        <Kpi label="Latência p95" valor={ms(p?.latencia_p95)}
             cor={p?.latencia_p95 > 10000 ? AMARELO : undefined}
             nota={`mediana ${ms(p?.latencia_p50)}`} />
        <Kpi label="Servido de cache" valor={pct(e?.taxa_cache)}
             cor={e?.taxa_cache > 0 ? VERDE : (v?.turnos ? VERMELHO : undefined)}
             nota={e?.taxa_cache > 0 ? 'caching a funcionar' : 'sem leituras de cache'} />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Cartao>
          <h3 className="text-sm font-medium text-zinc-200 mb-3">Desempenho</h3>
          <Linha label="Latência mediana (p50)" valor={ms(p?.latencia_p50)} />
          <Linha label="Latência p95" valor={ms(p?.latencia_p95)} />
          <Linha label="Latência máxima" valor={ms(p?.latencia_max)} />
          <Linha label="Iterações por turno" valor={(p?.iteracoes_media ?? 0).toFixed(2)}
                 nota="1 = sem tools" />
          <Linha label="Erros" valor={num(p?.erros)} nota={pct(p?.taxa_erro)} />
        </Cartao>

        <Cartao>
          <h3 className="text-sm font-medium text-zinc-200 mb-3">Tokens e contexto</h3>
          <Linha label="Input (preço cheio)" valor={num(e?.tokens_input)} />
          <Linha label="Lidos de cache" valor={num(e?.tokens_cache_read)} nota="10% do preço" />
          <Linha label="Escritos em cache" valor={num(e?.tokens_cache_write)} nota="125% do preço" />
          <Linha label="Output" valor={num(e?.tokens_output)} />
          <Linha label="Contexto médio por turno" valor={num(ctx?.input_medio)}
                 nota={`máx ${num(ctx?.input_max)}`} />
        </Cartao>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Cartao>
          <h3 className="text-sm font-medium text-zinc-200 mb-1">Tools chamadas</h3>
          <p className="text-xs text-zinc-600 mb-3">O que o assistente fez, não só o que disse.</p>
          <Barras dados={d.tools} />
        </Cartao>

        <Cartao>
          <h3 className="text-sm font-medium text-zinc-200 mb-1">Custo por canal</h3>
          <p className="text-xs text-zinc-600 mb-3">WhatsApp vs chat do painel.</p>
          <Barras dados={c?.por_canal} formato={v => usd(v)} />
        </Cartao>
      </div>

      <Cartao>
        <h3 className="text-sm font-medium text-zinc-200 mb-3">Acções pendentes</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-zinc-500">Visitas por confirmar</p>
            <p className="text-xl font-semibold text-zinc-100 tabular-nums">
              {num(d.accoes?.visitas_pendentes)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">Escaladas por tratar</p>
            <p className="text-xl font-semibold tabular-nums"
               style={{ color: d.accoes?.escaladas_pendentes ? AMARELO : '#f4f4f5' }}>
              {num(d.accoes?.escaladas_pendentes)}
            </p>
          </div>
        </div>
        <p className="text-xs text-zinc-600 mt-3">
          Contagem global (não filtrada por assistente) — ambas vivem em Imóveis → Tarefas.
        </p>
      </Cartao>
    </div>
  )
}
