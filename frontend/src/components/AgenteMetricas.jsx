import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Barras from './Barras'

// Cores validadas contra a superfície real dos cartões (zinc-900 #18181b).
const AZUL = '#3987e5'
const VERDE = '#0ca30c'
const VERMELHO = '#d03b3b'
const AMARELO = '#fab219'

const num = n => (n ?? 0).toLocaleString('pt-PT')
const usd = n => `$${(n ?? 0).toFixed(4)}`
const eur = n => `${Math.round(n ?? 0).toLocaleString('pt-PT')}€`
const ms = n => (n >= 1000 ? `${(n / 1000).toFixed(1)}s` : `${Math.round(n ?? 0)}ms`)

// Uma percentagem sobre 3 conversas não é um sinal — é ruído com ar de sinal.
// Abaixo deste limiar mostra-se sempre a fracção em bruto ao lado.
const AMOSTRA_MINIMA = 20
const taxa = (valor, numerador, denominador) => {
  const p = `${((valor ?? 0) * 100).toFixed(1)}%`
  return denominador && denominador < AMOSTRA_MINIMA
    ? `${p} (${num(numerador)} de ${num(denominador)})`
    : p
}

const PERIODOS = [{ dias: 7, label: '7 dias' }, { dias: 30, label: '30 dias' }, { dias: 90, label: '90 dias' }]

function Cartao({ children, className = '' }) {
  return <div className={`bg-zinc-900 border border-white/5 rounded-2xl p-5 ${className}`}>{children}</div>
}

function Bloco({ titulo, nota, children }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-white">{titulo}</h2>
        {nota && <p className="text-xs text-zinc-600 mt-0.5">{nota}</p>}
      </div>
      {children}
    </section>
  )
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
        {valor}{nota && <span className="text-xs text-zinc-600 ml-2">{nota}</span>}
      </span>
    </div>
  )
}

export default function AgenteMetricas({ agente }) {
  const [dias, setDias] = useState(30)
  const [d, setD] = useState(null)
  const [tecnico, setTecnico] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setD(null); setError('')
    api.get(`/api/agentes/metricas?agente=${agente}&dias=${dias}`)
      .then(setD)
      .catch(() => setError('Erro ao carregar métricas.'))
  }, [agente, dias])

  if (error) return <p className="text-red-400 text-sm">{error}</p>
  if (!d) return <p className="text-zinc-600 text-sm">A carregar…</p>

  const f = d.funil || {}, at = d.atendimento || {}, pr = d.preferencias || {}, op = d.operacional || {}
  const vazio = !op.turnos

  return (
    <div className="space-y-8">
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

      {vazio && (
        <div className="p-4 bg-zinc-900 border border-white/5 rounded-xl text-sm text-zinc-500">
          Sem turnos registados neste período. As conversas anteriores à
          instrumentação não têm dados de custo, latência nem preferências.
        </div>
      )}

      {/* ── 🌟 FUNIL ───────────────────────────── */}
      <Bloco titulo="🌟 Funil e conversão"
             nota="Do primeiro contacto até à visita marcada.">
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <Kpi label="Leads captados" valor={num(f.leads_captados)}
               nota={`${num(f.conversas)} conversas`} />
          <Kpi label="Leads qualificados" valor={num(f.mqls)} cor={AZUL}
               nota={`${taxa(f.taxa_qualificacao, f.mqls, f.leads_captados)} dos leads`} />
          <Kpi label="Visitas agendadas" valor={num(f.visitas_agendadas)} cor={VERDE} />
          <Kpi label="Taxa de conversão"
               valor={taxa(f.taxa_conversao, f.visitas_agendadas, f.conversas)}
               nota="visitas ÷ conversas" />
        </div>
        <p className="text-xs text-zinc-600">
          Qualificado = orçamento, zona e tipo de interesse declarados.
        </p>
      </Bloco>

      {/* ── 💬 ATENDIMENTO ─────────────────────── */}
      <Bloco titulo="💬 Desempenho e saúde do atendimento"
             nota="Rapidez, autonomia e envolvimento do cliente.">
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <Kpi label="Resposta (mediana)" valor={ms(at.tempo_resposta_p50)}
               nota={`p95 ${ms(at.tempo_resposta_p95)}`}
               cor={at.tempo_resposta_p95 > 10000 ? AMARELO : undefined} />
          <Kpi label="Transbordos" valor={num(at.transbordos)}
               cor={at.transbordos ? AMARELO : undefined}
               nota={`${taxa(at.taxa_transbordo, at.transbordos, f.conversas)} das conversas`} />
          <Kpi label="Mensagens por conversa"
               valor={(at.mensagens_por_conversa ?? 0).toFixed(1)}
               nota={`${num(at.conversas_longas)} com 8+`} />
          <Kpi label="Clientes recorrentes" valor={num(at.clientes_recorrentes)}
               nota="voltaram a escrever" />
        </div>

        <Cartao>
          <h3 className="text-sm font-medium text-zinc-200 mb-1">Motivos de transbordo</h3>
          <p className="text-xs text-zinc-600 mb-3">
            O que a IA não resolveu — é por aqui que se sabe o que treinar a seguir.
          </p>
          <Barras dados={at.motivos} cor={AMARELO} />
        </Cartao>
      </Bloco>

      {/* ── 🏠 PREFERÊNCIAS ────────────────────── */}
      <Bloco titulo="🏠 Preferências do mercado"
             nota={`De ${num(pr.pesquisas)} pesquisas — inclui quem procurou e nunca deixou contacto.`}>
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <Kpi label="Preço médio pedido" valor={eur(pr.preco_medio_pedido)}
               nota={`mediana ${eur(pr.preco_mediano_pedido)}`} />
          <Kpi label="Orçamento declarado" valor={eur(pr.orcamento_medio_declarado)}
               nota="médio, de quem se registou" />
          <Kpi label="Pesquisas" valor={num(pr.pesquisas)} />
          <Kpi label="Zonas distintas" valor={num(pr.zonas?.length)} />
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          <Cartao>
            <h3 className="text-sm font-medium text-zinc-200 mb-3">Zonas mais procuradas</h3>
            <Barras dados={pr.zonas} />
          </Cartao>
          <Cartao>
            <h3 className="text-sm font-medium text-zinc-200 mb-3">Tipologias</h3>
            <Barras dados={pr.tipologias} />
          </Cartao>
          <Cartao>
            <h3 className="text-sm font-medium text-zinc-200 mb-3">Intenção</h3>
            <Barras dados={pr.intencao} />
          </Cartao>
        </div>
      </Bloco>

      {/* ── ⚙️ OPERACIONAL ─────────────────────── */}
      <Bloco titulo="⚙️ Estado operacional"
             nota="Volume, custo e fiabilidade.">
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <Kpi label="Custo total" valor={usd(op.custo_total_usd)} cor={AZUL}
               nota={`${num(op.turnos)} turnos`} />
          <Kpi label="Custo por interação" valor={usd(op.custo_por_interacao)} />
          <Kpi label="Taxa de sucesso"
               valor={taxa(op.taxa_sucesso, (op.turnos ?? 0) - (op.erros ?? 0), op.turnos)}
               cor={op.erros ? VERMELHO : VERDE}
               nota={op.erros ? `${num(op.erros)} erros` : 'sem erros'} />
          <Kpi label="Servido de cache"
               valor={`${((op.taxa_cache ?? 0) * 100).toFixed(1)}%`}
               cor={op.taxa_cache > 0 ? VERDE : (op.turnos ? VERMELHO : undefined)}
               nota={op.taxa_cache > 0 ? 'caching a funcionar' : 'sem leituras de cache'} />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <Cartao>
            <h3 className="text-sm font-medium text-zinc-200 mb-3">Volume por canal</h3>
            <Barras dados={op.por_canal} />
          </Cartao>
          <Cartao>
            <h3 className="text-sm font-medium text-zinc-200 mb-3">Tools chamadas</h3>
            <Barras dados={op.tools} />
          </Cartao>
        </div>

        <Cartao>
          <div className="flex items-baseline justify-between gap-3">
            <div>
              <p className="text-xs text-zinc-400">Última interação</p>
              <p className="text-sm text-zinc-200">
                {op.ultima_interacao
                  ? new Date(op.ultima_interacao).toLocaleString('pt-PT')
                  : '—'}
              </p>
            </div>
            <p className="text-xs text-zinc-600 max-w-sm text-right">
              Não há medição de uptime aqui — precisaria de uma sonda externa.
              A disponibilidade real está no painel do Fly.io.
            </p>
          </div>
        </Cartao>

        <button onClick={() => setTecnico(t => !t)}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
          {tecnico ? '− Ocultar' : '+ Mostrar'} detalhe técnico
        </button>

        {tecnico && (
          <Cartao>
            <Linha label="Tokens input (preço cheio)" valor={num(op.tokens_input)} />
            <Linha label="Lidos de cache" valor={num(op.tokens_cache_read)} nota="10% do preço" />
            <Linha label="Escritos em cache" valor={num(op.tokens_cache_write)} nota="125% do preço" />
            <Linha label="Tokens output" valor={num(op.tokens_output)} />
            <Linha label="Contexto médio por turno" valor={num(op.contexto_medio)}
                   nota={`máx ${num(op.contexto_max)}`} />
            <Linha label="Iterações por turno" valor={(at.iteracoes_media ?? 0).toFixed(2)}
                   nota="1 = sem tools" />
          </Cartao>
        )}
      </Bloco>
    </div>
  )
}
