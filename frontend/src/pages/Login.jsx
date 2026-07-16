import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { pt } from '../i18n/pt'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)

    const { error } = await supabase.auth.signInWithPassword({ email, password })

    setLoading(false)

    if (error) {
      setError(pt.auth.loginError)
    } else {
      navigate('/')
    }
  }

  return (
    <div
      className="relative min-h-screen flex items-center justify-center bg-cover bg-center"
      style={{ backgroundImage: "url('/marina_por_do_sol.jpg')" }}
    >
      {/* dark overlay */}
      <div className="absolute inset-0 bg-black/50" />

      <div className="relative z-10 px-12 py-10 w-full max-w-sm">
        <div className="inline-block mb-2">
          <h1 className="text-5xl font-light text-white text-center">Figueirahome</h1>
          <p className="text-white text-lg text-center">Agent OS</p>
        </div>
        <p className="text-white/70 text-base mb-10">Painel de Gestão</p>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Email field */}
          <div className="flex items-center border-b border-white/50 pb-2 gap-3">
            <svg className="w-5 h-5 text-white/70 shrink-0" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
            </svg>
            <input
              type="email"
              required
              placeholder={pt.auth.email}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-1 bg-transparent text-white placeholder-white/60 text-sm focus:outline-none"
            />
          </div>

          {/* Password field */}
          <div className="flex items-center border-b border-white/50 pb-2 gap-3">
            <svg className="w-5 h-5 text-white/70 shrink-0" fill="currentColor" viewBox="0 0 24 24">
              <path d="M18 8h-1V6c0-2.8-2.2-5-5-5S7 3.2 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.7 1.4-3.1 3.1-3.1 1.7 0 3.1 1.4 3.1 3.1v2z"/>
            </svg>
            <input
              type="password"
              required
              placeholder={pt.auth.password}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="flex-1 bg-transparent text-white placeholder-white/60 text-sm focus:outline-none"
            />
          </div>

          {error && (
            <p className="text-red-300 text-sm -mt-4">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-500 hover:bg-blue-600 text-white font-semibold py-3 rounded text-sm tracking-widest uppercase transition-colors disabled:opacity-50"
          >
            {loading ? pt.common.loading : pt.auth.login}
          </button>
        </form>
      </div>
    </div>
  )
}
