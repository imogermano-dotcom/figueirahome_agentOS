import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

export default function Agente2() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef()

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput(''); setError('')
    setMessages(m => [...m, { role: 'user', content: text }])
    setLoading(true)
    try {
      const data = await api.post('/api/broker/chat', { mensagem: text, participante: 'painel_web' })
      setMessages(m => [...m, { role: 'assistant', content: data.resposta }])
    } catch (err) { setError(err.message) }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-white">Assistente Broker</h1>
        <p className="text-zinc-500 text-sm mt-0.5">Consulta clientes, imóveis e leads em linguagem natural.</p>
      </div>

      <div className="flex-1 bg-zinc-900 border border-white/5 rounded-2xl overflow-y-auto p-4 space-y-3 mb-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-4xl mb-3">💬</p>
              <p className="text-zinc-500 text-sm">
                Pergunta sobre clientes, imóveis ou leads.<br />
                <span className="text-zinc-600">Ex: "Que clientes estão à procura de moradias em Torres Novas?"</span>
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
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="Escreve a tua pergunta…" disabled={loading}
          className="flex-1 bg-zinc-900 border border-zinc-800 text-zinc-100 placeholder-zinc-600 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors" />
        <button type="submit" disabled={loading || !input.trim()}
          className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-5 py-2.5 rounded-xl disabled:opacity-50 transition-all shadow-lg shadow-blue-500/20">
          Enviar
        </button>
      </form>
    </div>
  )
}
