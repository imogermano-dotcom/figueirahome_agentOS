import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Barras from '../components/Barras'

// Cores validadas com o validador da skill dataviz contra a superfície real
// dos cartões (zinc-900 #18181b), não contra a superfície default.
// A ordem da barra do pipeline é Perdida · Ativa · Ganha de propósito: verde e
// vermelho lado a lado dão ΔE 4,1 sob daltonismo (um deuteranope não distingue
// "ganha" de "perdida"). Com o azul no meio, o pior par adjacente é ΔE 25,7.
const AZUL = '#3987e5'      // série / neutro
const VERDE = '#0ca30c'     // bom
const VERMELHO = '#d03b3b'  // crítico
const AMARELO = '#fab219'   // aviso

const nf = n => (n ?? 0).toLocaleString('pt-PT')

function Cartao({ children, className = '' }) {
  return (
    <div className={`bg-zinc-900 border border-white/5 rounded-2xl p-5 ${className}`}>
      {children}
    </div>
  )
}

function Titulo({ children, nota }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-medium text-zinc-200">{children}</h2>
      {nota && <p className="text-xs text-zinc-600 mt-0.5">{nota}</p>}
    </div>
  )
}

function Kpi({ label, valor, nota, cor }) {
  return (
    <Cartao>
      <p className="text-zinc-500 text-xs uppercase tracking-widest mb-2">{label}</p>
      <p className="text-3xl font-bold" style={{ color: cor || '#fff' }}>{nf(valor)}</p>
      {nota && <p className="text-xs text-zinc-600 mt-1">{nota}</p>}
    </Cartao>
  )
}

// Barra empilhada parte-para-todo. Cada segmento leva rótulo directo —
// a cor nunca carrega o significado sozinha.
function Pipeline({ o }) {
  const total = o?.total || 0
  const segmentos = [
    { nome: 'Perdidas', valor: o?.perdidas, cor: VERMELHO, icone: '✕' },
    { nome: 'Activas',  valor: o?.ativas,   cor: AZUL,     icone: '•' },
    { nome: 'Ganhas',   valor: o?.ganhas,   cor: VERDE,    icone: '✓' },
  ].filter(s => s.valor > 0)

  return (
    <Cartao>
      <Titulo nota={`${nf(total)} oportunidades no CRM`}>Pipeline</Titulo>

      <div className="flex gap-0.5 h-3 mb-4">
        {segmentos.map(s => (
          <div
            key={s.nome}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{ width: `${(s.valor / total) * 100}%`, background: s.cor }}
            title={`${s.nome}: ${nf(s.valor)}`}
          />
        ))}
      </div>

      <ul className="grid grid-cols-3 gap-3">
        {segmentos.map(s => (
          <li key={s.nome}>
            <div className="flex items-center gap-1.5 mb-0.5">
              <span style={{ color: s.cor }} aria-hidden="true">{s.icone}</span>
              <span className="text-xs text-zinc-400">{s.nome}</span>
            </div>
            <p className="text-lg font-semibold text-zinc-100 tabular-nums">{nf(s.valor)}</p>
            <p className="text-xs text-zinc-600">{((s.valor / total) * 100).toFixed(1)}%</p>
          </li>
        ))}
      </ul>
    </Cartao>
  )
}

function Sync({ linhas }) {
  if (!linhas?.length) return <p className="text-sm text-zinc-600">Sem execuções registadas.</p>

  return (
    <ul className="space-y-3">
      {linhas.map(l => {
        const erros = l.resumo?.erros ?? 0
        const horas = (Date.now() - new Date(l.executado_em)) / 36e5
        // Falha = erros reportados, ou silêncio há mais de 48h num sync diário.
        const mau = erros > 0 || horas > 48
        return (
          <li key={l.tipo} className="flex items-start gap-2.5">
            <span style={{ color: mau ? VERMELHO : VERDE }} aria-hidden="true">
              {mau ? '▲' : '●'}
            </span>
            <div className="min-w-0">
              <p className="text-xs text-zinc-300 truncate">{l.tipo}</p>
              <p className="text-xs text-zinc-600">
                {new Date(l.executado_em).toLocaleString('pt-PT')}
                {' · '}
                <span style={{ color: mau ? VERMELHO : undefined }}>
                  {erros > 0 ? `${erros} erros` : mau ? 'sem correr há >48h' : 'sem erros'}
                </span>
              </p>
              <p className="text-xs text-zinc-600 mt-0.5">
                {Object.entries(l.resumo || {})
                  .filter(([k]) => k !== 'erros')
                  .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
                  .join(' · ')}
              </p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export default function Dashboard() {
  const [d, setD] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/api/dashboard')
      .then(setD)
      .catch(() => setError('Erro ao carregar métricas.'))
  }, [])

  if (error) return <p className="text-red-400 text-sm">{error}</p>
  if (!d) return <p className="text-zinc-600 text-sm">A carregar…</p>

  const { oportunidades: o, imoveis: i, assistentes: a, alertas: al } = d

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-zinc-500 text-sm mt-1">Resumo da actividade</p>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <Kpi label="Oportunidades activas" valor={o?.ativas} nota={`de ${nf(o?.total)} no total`} />
        <Kpi label="Imóveis publicados" valor={i?.publicados} cor={AZUL}
             nota={`${nf(i?.disponiveis)} marcados disponíveis`} />
        <Kpi label="Contactos" valor={d.contactos} />
        <Kpi label="Tarefas pendentes" valor={a?.tarefas_pendentes}
             nota={a?.visitas_pendentes ? `${nf(a.visitas_pendentes)} visitas por confirmar` : null} />
      </div>

      <Pipeline o={o} />

      <div className="grid lg:grid-cols-2 gap-4">
        <Cartao>
          <Titulo nota="Top 8; a cauda agrupada em Outros">Oportunidades por responsável</Titulo>
          <Barras dados={d.por_responsavel} />
        </Cartao>
        <Cartao>
          <Titulo nota="Top 7; a cauda agrupada em Outros">Oportunidades por origem</Titulo>
          <Barras dados={d.por_origem} />
        </Cartao>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Cartao>
          <Titulo nota={`${nf(i?.total)} imóveis na base de dados`}>Portefólio</Titulo>
          <Barras dados={[
            { nome: 'Publicados no site', total: i?.publicados || 0 },
            { nome: 'Disponível', total: i?.disponiveis || 0 },
            { nome: 'Em prospecção', total: i?.prospeccao || 0 },
            { nome: 'Por validar', total: i?.por_validar || 0 },
            { nome: 'Retirados', total: i?.retirados || 0 },
          ]} />
        </Cartao>

        <Cartao>
          <Titulo nota="Conversas, visitas e escaladas">Assistentes IA</Titulo>
          <div className="grid grid-cols-3 gap-3 mb-4">
            {[
              ['Conversas', a?.conversas_total],
              ['Visitas', a?.visitas_pendentes],
              ['Escaladas', a?.escalar_pendentes],
            ].map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-zinc-500">{k}</p>
                <p className="text-xl font-semibold text-zinc-100 tabular-nums">{nf(v)}</p>
              </div>
            ))}
          </div>
          <Barras dados={a?.conversas_por_agente} />
        </Cartao>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Cartao>
          <Titulo nota="Última execução de cada pipeline">Sincronizações</Titulo>
          <Sync linhas={d.sync} />
        </Cartao>

        <Cartao>
          <Titulo nota="Registos incompletos — não bloqueiam, mas limitam o que se pode medir">
            A precisar de atenção
          </Titulo>
          <ul className="space-y-2.5">
            {[
              ['Imóveis com fonte "manual"', al?.imoveis_fonte_manual, 'origem por confirmar'],
              ['Imóveis em prospecção', al?.imoveis_prospeccao, 'nunca publicados'],
              ['Oportunidades sem etapa', al?.oport_sem_etapa, 'ficam fora de qualquer funil'],
              ['Oportunidades sem data', al?.oport_sem_data, 'impedem gráficos de evolução'],
              ['Oportunidades sem responsável', al?.oport_sem_responsavel, null],
            ].filter(([, v]) => v > 0).map(([k, v, nota]) => (
              <li key={k} className="flex items-start gap-2.5">
                <span style={{ color: AMARELO }} aria-hidden="true">▲</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-xs text-zinc-300">{k}</span>
                    <span className="text-xs text-zinc-200 tabular-nums shrink-0">{nf(v)}</span>
                  </div>
                  {nota && <p className="text-xs text-zinc-600">{nota}</p>}
                </div>
              </li>
            ))}
          </ul>
        </Cartao>
      </div>
    </div>
  )
}
