import { NavLink } from 'react-router-dom'
import { pt } from '../i18n/pt'
import { supabase } from '../lib/supabase'

const navItems = [
  { to: '/', label: pt.nav.dashboard, icon: '▦' },
  { to: '/agente1', label: pt.nav.agente1, icon: '☎' },
  { to: '/agente2', label: pt.nav.agente2, icon: '💬' },
  { to: '/clientes', label: pt.nav.clientes, icon: '👥' },
  { to: '/imoveis', label: pt.nav.imoveis, icon: '🏠' },
  { to: '/leads', label: pt.nav.leads, icon: '📋' },
  { to: '/config', label: pt.nav.config, icon: '⚙' },
]

export default function Sidebar() {
  async function handleLogout() {
    await supabase.auth.signOut()
  }

  return (
    <aside className="w-56 shrink-0 bg-zinc-900 border-r border-white/5 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-6 border-b border-white/5">
        <span className="font-bold text-base tracking-tight bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
          Figueirahome
        </span>
        <p className="text-white text-xs mt-0.5">Agent OS</p>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto space-y-0.5 px-2">
        {navItems.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-blue-600/30 to-violet-600/20 text-white border border-white/10'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
              }`
            }
          >
            <span className="text-base leading-none">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-white/5">
        <button
          onClick={handleLogout}
          className="w-full text-left text-xs text-zinc-600 hover:text-zinc-300 transition-colors"
        >
          {pt.auth.logout}
        </button>
      </div>
    </aside>
  )
}
