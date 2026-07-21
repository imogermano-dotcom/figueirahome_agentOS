import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const cards = [
  {
    key: 'chamadas_hoje',
    label: 'Chamadas hoje',
    icon: '☎',
    gradient: 'from-blue-500 to-blue-700',
    glow: 'shadow-blue-500/20',
    text: 'from-blue-300 to-blue-500',
  },
  {
    key: 'leads_novos',
    label: 'Leads novos',
    icon: '📋',
    gradient: 'from-emerald-500 to-emerald-700',
    glow: 'shadow-emerald-500/20',
    text: 'from-emerald-300 to-emerald-500',
  },
  {
    key: 'imoveis_disponiveis',
    label: 'Imóveis disponíveis',
    icon: '🏠',
    gradient: 'from-violet-500 to-violet-700',
    glow: 'shadow-violet-500/20',
    text: 'from-violet-300 to-violet-500',
  },
  {
    key: 'conversas_hoje',
    label: 'Conversas hoje',
    icon: '💬',
    gradient: 'from-amber-500 to-orange-600',
    glow: 'shadow-amber-500/20',
    text: 'from-amber-300 to-orange-400',
  },
  {
    key: 'tarefas_pendentes',
    label: 'Tarefas pendentes',
    icon: '✓',
    gradient: 'from-rose-500 to-pink-600',
    glow: 'shadow-rose-500/20',
    text: 'from-rose-300 to-pink-400',
  },
]

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/api/dashboard')
      .then(setData)
      .catch(() => setError('Erro ao carregar métricas.'))
  }, [])

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-zinc-500 text-sm mt-1">Resumo da actividade</p>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {cards.map(card => (
          <div
            key={card.key}
            className={`relative bg-zinc-900 border border-white/5 rounded-2xl p-5 overflow-hidden shadow-lg ${card.glow}`}
          >
            {/* gradient blob */}
            <div className={`absolute -top-6 -right-6 w-24 h-24 rounded-full bg-gradient-to-br ${card.gradient} opacity-20 blur-2xl`} />

            <div className={`inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br ${card.gradient} text-lg mb-4 shadow-md`}>
              {card.icon}
            </div>

            <p className="text-zinc-500 text-xs uppercase tracking-widest mb-1">{card.label}</p>
            <p className={`text-4xl font-bold bg-gradient-to-r ${card.text} bg-clip-text text-transparent`}>
              {data ? (data[card.key] ?? 0) : '—'}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
