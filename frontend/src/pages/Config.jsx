export default function Config() {
  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Configuração</h1>
        <p className="text-zinc-500 text-sm mt-1">Credenciais e definições gerais do sistema.</p>
      </div>
      <div className="bg-zinc-900 border border-white/5 rounded-2xl p-6 space-y-4">
        {[
          { label: 'Telnyx API Key', key: 'TELNYX_API_KEY', status: false },
          { label: 'Telnyx Public Key', key: 'TELNYX_PUBLIC_KEY', status: false },
          { label: 'Telnyx Phone Number', key: 'TELNYX_PHONE_NUMBER', status: false },
          { label: 'Meta WhatsApp Token', key: 'META_WHATSAPP_TOKEN', status: true },
          { label: 'Meta Phone Number ID', key: 'META_PHONE_NUMBER_ID', status: true },
          { label: 'Anthropic API Key', key: 'ANTHROPIC_API_KEY', status: true },
          { label: 'OpenAI API Key', key: 'OPENAI_API_KEY', status: true },
          { label: 'Supabase URL', key: 'SUPABASE_URL', status: true },
        ].map(item => (
          <div key={item.key} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
            <div>
              <p className="text-sm text-zinc-200">{item.label}</p>
              <p className="text-xs text-zinc-600 font-mono">{item.key}</p>
            </div>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${item.status ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/15 text-red-400 border border-red-500/20'}`}>
              {item.status ? 'Configurado' : 'Em falta'}
            </span>
          </div>
        ))}
      </div>
      <p className="text-zinc-600 text-xs mt-4">Editar credenciais directamente no ficheiro <code className="font-mono bg-zinc-800 px-1 rounded">backend/.env</code></p>
    </div>
  )
}
