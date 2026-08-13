import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Field, Modal, fmtEuro, inputCls, selectCls } from './ui'

/* Base do URL público. O Worker da Cloudflare faz proxy de `site.pt/imovel/*`
 * para `/lp/*` no backend; enquanto não estiver posto, cai no URL da API, que
 * também serve as páginas. */
const LANDING_BASE = import.meta.env.VITE_LANDING_BASE_URL || import.meta.env.VITE_API_BASE_URL

const EMPTY_FORM = { imovel_ref: '', mostrar_preco: true, video_url: '', mapa_url: '', notas: '' }

function fmtData(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-PT', { day: '2-digit', month: 'short', year: 'numeric' })
}

function urlPublico(slug) {
  return `${LANDING_BASE}/lp/${slug}`
}

export default function LandingPagesTab() {
  const [paginas, setPaginas] = useState([])
  const [imoveis, setImoveis] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(null)   // null | 'nova' | imovel_ref a editar
  const [form, setForm] = useState(EMPTY_FORM)
  const [ocupado, setOcupado] = useState(null)  // imovel_ref ou 'nova' — geração em curso
  const [error, setError] = useState('')
  const [copiado, setCopiado] = useState('')

  async function load() {
    setLoading(true)
    try { setPaginas(await api.get('/api/landing-pages')) }
    catch { setError('Erro ao carregar landing pages.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function abrirNova() {
    setError(''); setForm(EMPTY_FORM); setModal('nova')
    if (!imoveis.length) {
      try { setImoveis(await api.get('/api/imoveis?disponibilidade=Disponível')) }
      catch { setError('Erro ao carregar imóveis.') }
    }
  }

  function abrirEdicao(p) {
    setError('')
    setForm({
      imovel_ref: p.imovel_ref,
      mostrar_preco: p.mostrar_preco,
      video_url: p.extras?.video_url || '',
      mapa_url: p.extras?.mapa_url || '',
      notas: p.extras?.notas || '',
    })
    setModal(p.imovel_ref)
  }

  function extrasDoForm() {
    const extras = {}
    for (const campo of ['video_url', 'mapa_url', 'notas']) {
      if (form[campo].trim()) extras[campo] = form[campo].trim()
    }
    return extras
  }

  async function guardar() {
    if (!form.imovel_ref) { setError('Escolhe um imóvel.'); return }
    setOcupado(modal); setError('')
    const corpo = { mostrar_preco: form.mostrar_preco, extras: extrasDoForm() }
    try {
      if (modal === 'nova') await api.post('/api/landing-pages', { ...corpo, imovel_ref: form.imovel_ref })
      else await api.put(`/api/landing-pages/${form.imovel_ref}`, corpo)
      setModal(null); await load()
    } catch (err) { setError(err.message) }
    setOcupado(null)
  }

  async function regenerar(ref) {
    setOcupado(ref); setError('')
    try {
      const r = await api.post(`/api/landing-pages/${ref}/regenerar?forcar=true`)
      if (r) await load()
    } catch (err) { setError(err.message) }
    setOcupado(null)
  }

  async function remover(ref) {
    if (!confirm(`Remover a landing page de ${ref}? O link deixa de funcionar.`)) return
    try { await api.delete(`/api/landing-pages/${ref}`); await load() }
    catch (err) { setError(err.message) }
  }

  async function copiar(slug) {
    await navigator.clipboard.writeText(urlPublico(slug))
    setCopiado(slug)
    setTimeout(() => setCopiado(''), 2000)
  }

  const custoTotal = paginas.reduce((s, p) => s + Number(p.custo_usd || 0), 0)
  const semPagina = imoveis.filter(i => !paginas.some(p => p.imovel_ref === i.imovel_ref))

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <div>
          <p className="text-zinc-400 text-sm">
            {paginas.length} {paginas.length === 1 ? 'página' : 'páginas'}
            {custoTotal > 0 && <span className="text-zinc-600"> · ${custoTotal.toFixed(2)} em geração</span>}
          </p>
        </div>
        <button onClick={abrirNova}
          className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20">
          Nova landing page
        </button>
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      {loading ? (
        <p className="text-zinc-500 text-sm">A carregar…</p>
      ) : paginas.length === 0 ? (
        <div className="bg-zinc-900 border border-white/5 rounded-2xl p-8 text-center">
          <p className="text-zinc-400 text-sm">Ainda não há landing pages.</p>
          <p className="text-zinc-600 text-xs mt-1">
            Cria uma por imóvel que vá a anúncio — o texto é escrito pela IA a partir dos dados do eGO.
          </p>
        </div>
      ) : (
        <div className="bg-zinc-900 border border-white/5 rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-zinc-400">
              <tr>
                <th className="text-left font-medium px-4 py-3">Imóvel</th>
                <th className="text-left font-medium px-4 py-3">Estado</th>
                <th className="text-left font-medium px-4 py-3">Gerada</th>
                <th className="text-right font-medium px-4 py-3">Leads</th>
                <th className="text-right font-medium px-4 py-3">Custo</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {paginas.map(p => {
                const publicado = p.imovel?.publicado
                const aTrabalhar = ocupado === p.imovel_ref
                return (
                  <tr key={p.imovel_ref} className="border-t border-white/5">
                    <td className="px-4 py-3">
                      <p className="text-zinc-100 font-medium">{p.imovel_ref}</p>
                      <p className="text-zinc-500 text-xs">
                        {p.imovel?.natureza}{p.imovel?.quartos != null && ` T${p.imovel.quartos}`}
                        {p.imovel?.concelho && ` · ${p.imovel.concelho}`}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      {/* Estado vem de `imoveis.publicado`, não de uma coluna própria:
                          a página mostra "já não disponível" sozinha quando isto cai. */}
                      <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md ${
                        publicado
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                          : 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
                      }`}>
                        <span aria-hidden="true">●</span>
                        {publicado ? 'No ar' : 'Já não disponível'}
                      </span>
                      {!p.mostrar_preco && (
                        <span className="ml-2 text-xs text-zinc-500">preço escondido</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-400">{fmtData(p.gerado_em)}</td>
                    <td className="px-4 py-3 text-right text-zinc-100 font-medium tabular-nums">{p.leads || 0}</td>
                    <td className="px-4 py-3 text-right text-zinc-500 tabular-nums">
                      {p.custo_usd ? `$${Number(p.custo_usd).toFixed(3)}` : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-3 text-xs">
                        <a href={urlPublico(p.slug)} target="_blank" rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 transition-colors">Abrir</a>
                        <button onClick={() => copiar(p.slug)} className="text-zinc-400 hover:text-zinc-200 transition-colors">
                          {copiado === p.slug ? 'Copiado' : 'Copiar link'}
                        </button>
                        <button onClick={() => abrirEdicao(p)} disabled={aTrabalhar}
                          className="text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40">Editar</button>
                        <button onClick={() => regenerar(p.imovel_ref)} disabled={aTrabalhar}
                          className="text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-40">
                          {aTrabalhar ? 'A gerar…' : 'Regenerar'}
                        </button>
                        <button onClick={() => remover(p.imovel_ref)} disabled={aTrabalhar}
                          className="text-red-500 hover:text-red-400 transition-colors disabled:opacity-40">Remover</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <Modal title={modal === 'nova' ? 'Nova landing page' : `Landing page ${form.imovel_ref}`} onClose={() => setModal(null)}>
          <div className="space-y-4">
            {modal === 'nova' && (
              <Field label="Imóvel">
                <select className={selectCls} value={form.imovel_ref}
                  onChange={e => setForm({ ...form, imovel_ref: e.target.value })}>
                  <option value="">Escolher…</option>
                  {semPagina.map(i => (
                    <option key={i.imovel_ref} value={i.imovel_ref}>
                      {i.imovel_ref} — {i.natureza}{i.quartos != null && ` T${i.quartos}`}
                      {i.concelho && `, ${i.concelho}`} — {fmtEuro(i.venda_preco || i.arrendamento_preco)}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" checked={form.mostrar_preco}
                onChange={e => setForm({ ...form, mostrar_preco: e.target.checked })}
                className="mt-0.5 accent-blue-500" />
              <span>
                <span className="text-sm text-zinc-200">Mostrar o preço na página</span>
                <span className="block text-xs text-zinc-500">
                  Visível qualifica (quem não tem orçamento não preenche). Escondido usa o imóvel como chamariz.
                </span>
              </span>
            </label>

            <p className="text-xs text-zinc-500 border-t border-white/5 pt-4">
              O que o eGO não tem. Entra no texto gerado e na página.
            </p>

            <Field label="Vídeo (URL)">
              <input className={inputCls} placeholder="https://youtu.be/…" value={form.video_url}
                onChange={e => setForm({ ...form, video_url: e.target.value })} />
            </Field>
            <Field label="Mapa (URL)">
              <input className={inputCls} placeholder="Vazio = link automático para a morada" value={form.mapa_url}
                onChange={e => setForm({ ...form, mapa_url: e.target.value })} />
            </Field>
            <Field label="Notas do consultor">
              <textarea className={inputCls} rows={4} value={form.notas}
                placeholder="O que a ficha do eGO não diz e vale a pena vender."
                onChange={e => setForm({ ...form, notas: e.target.value })} />
            </Field>

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <div className="flex justify-end gap-3 pt-2">
              <button onClick={() => setModal(null)} className="text-sm text-zinc-400 hover:text-zinc-200 px-4 py-2 transition-colors">
                Cancelar
              </button>
              <button onClick={guardar} disabled={ocupado !== null}
                className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50">
                {ocupado !== null ? 'A gerar…' : modal === 'nova' ? 'Criar e gerar' : 'Guardar'}
              </button>
            </div>
            {ocupado !== null && (
              <p className="text-xs text-zinc-500 text-right">A escrita do conteúdo demora ~15 segundos.</p>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
