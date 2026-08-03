// Barras horizontais para comparar magnitude.
//
// Sem biblioteca de gráficos: isto são rectângulos, e o Recharts custaria
// ~100 kB para os desenhar. As barras vêm ordenadas por valor, por isso é o
// COMPRIMENTO que codifica a magnitude — a cor não repete essa informação
// (um ramp de azuis seria informação duplicada, e os passos não passavam a
// validação de contraste na superfície zinc-900).

const AZUL = '#3987e5'

export default function Barras({ dados, cor = AZUL, formato = v => v.toLocaleString('pt-PT') }) {
  if (!dados?.length) {
    return <p className="text-sm text-zinc-600">Sem dados.</p>
  }

  const max = Math.max(...dados.map(d => d.total), 1)  // nunca dividir por zero

  return (
    <ul className="space-y-2.5">
      {dados.map(({ nome, total }) => (
        <li key={nome}>
          <div className="flex items-baseline justify-between gap-3 mb-1">
            <span className="text-xs text-zinc-400 truncate" title={nome}>{nome}</span>
            <span className="text-xs text-zinc-300 tabular-nums shrink-0">{formato(total)}</span>
          </div>
          <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${Math.max((total / max) * 100, 1.5)}%`, background: cor }}
              title={`${nome}: ${formato(total)}`}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}
