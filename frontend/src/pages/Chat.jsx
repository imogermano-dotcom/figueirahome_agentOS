import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

// `agente: null` = deixa o router decidir. É assim que se testa o roteamento
// a partir do painel, sem depender do WhatsApp real.
const OPCOES = [
  { valor: 'broker',      label: 'Broker (interno)' },
  { valor: 'a1_vendedor', label: 'A1 — Vendedor' },
  { valor: 'a2_geral',    label: 'A2 — Atendimento Geral' },
  { valor: 'auto',        label: 'Auto (router)' },
]

const SUGESTAO = {
  broker:      'Ex: "Que imóveis tenho em Coimbra abaixo de 200 mil?"',
  a1_vendedor: 'Ex: "Procuro um T2 na Figueira até 150 mil"',
  a2_geral:    'Ex: "Qual é o vosso horário?"',
  auto:        'Escreve como um cliente — o router escolhe quem responde.',
}

export default function Chat() {
  const [agente, setAgente] = useState('broker')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef()

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // Cada assistente tem a sua thread — trocar de assistente limpa o ecrã,
  // não mistura contextos.
  useEffect(() => { setMessages([]); setError('') }, [agente])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput(''); setError('')
    setMessages(m => [...m, { role: 'user', content: text }])
    setLoading(true)
    try {
      const data = await api.post('/api/broker/chat', {
        mensagem: text,
        participante: `painel_${agente}`,
        agente: agente === 'auto' ? null : agente,
      })
      setMessages(m => [...m, { role: 'assistant', content: data.resposta }])
    } catch (err) { setError(err.message) }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Chat de Assistentes</h1>
          <p className="text-zinc-500 text-sm mt-0.5">{SUGESTAO[agente]}</p>
        </div>
        <select
          value={agente}
          onChange={e => setAgente(e.target.value)}
          className="bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors"
        >
          {OPCOES.map(o => <option key={o.valor} value={o.valor}>{o.label}</option>)}
        </select>
      </div>

      <div className="flex-1 bg-zinc-900 border border-white/5 rounded-2xl overflow-y-auto p-4 space-y-3 mb-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-4xl mb-3">💬</p>
              <p className="text-zinc-500 text-sm">
                {OPCOES.find(o => o.valor === agente)?.label}<br />
                <span className="text-zinc-600">{SUGESTAO[agente]}</span>
              </p>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
              msg.role === 'user'
                ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-br-sm'
                : 'bg-zinc-800 border border-white/5 text-zinc-200 rounded-bl-sm'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-zinc-800 border border-white/5 text-zinc-500 px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="inline-block w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="inline-block w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && <p className="text-red-400 text-sm mb-2">{error}</p>}

      <form onSubmit={handleSend} className="flex gap-3">
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="Escreve a tua mensagem…" disabled={loading}
          className="flex-1 bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors" />
        <button type="submit" disabled={loading || !input.trim()}
          className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-5 py-2.5 rounded-xl disabled:opacity-50 transition-all shadow-lg shadow-blue-500/20">
          Enviar
        </button>
      </form>
    </div>
  )
}
