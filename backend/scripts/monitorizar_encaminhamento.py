"""Há vendedores ou candidatos presos no assistente errado? (só leitura)

Responde a uma pergunta: **o regex do router está a deixar pessoas na Matilde (A1)
ou na Maria (A2) quando deviam estar na Bárbara (A4) ou na Inês (A3)?** É a medição
que falta para decidir se vale a pena o encaminhamento pelo modelo
(`docs/fases/encaminhamento-pelo-modelo-plano.md`). Não escreve em lado nenhum.

    cd backend && python scripts/monitorizar_encaminhamento.py [--dias 90] [--texto]

Por omissão **não imprime texto de mensagens** (podem ter nomes e telefones):
só ids curtos, datas, canal e qual o sinal. `--texto` mostra 90 caracteres da
mensagem que disparou o sinal — usar só localmente.

Os sinais são heurísticos e de propósito conservadores com "à venda"/"consultor"
(um comprador também os diz): é uma lista para olhar à mão, não um veredicto.
Só contam como desvio as conversas **depois** de a Bárbara (13/09) e a Inês
(20/09) existirem; as anteriores aparecem à parte.
"""

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.router import A1, A2, A3, A4, route  # noqa: E402
from app.db.supabase_client import get_supabase  # noqa: E402

_PAGINA = 1000  # limite por omissão do PostgREST
_A4_DESDE = "2026-09-13"  # Bárbara em produção
_A3_DESDE = "2026-09-20"  # Inês em produção
_NOME = {A1: "A1 Matilde", A2: "A2 Maria", A3: "A3 Inês", A4: "A4 Bárbara", None: "(sem agente)"}

# O dono do imóvel: possessivo ou "para vender/arrendar" na mesma frase. "À venda"
# sozinho não conta (um comprador diz "uma moradia à venda").
_VENDEDOR = re.compile(
    r"quero vender|pretendo vender|penso vender|vender (a minha|o meu|um|uma)\b|"
    r"tenho (um|uma|o|a)\b[^.?!]{0,40}para (vender|arrendar)|"
    r"quanto vale|avalia[çc]|angaria|"
    r"(meu|minha)\b[^.?!]{0,30}\b[àa] venda|colocar[^.?!]{0,30}\b[àa] venda|"
    r"arrendar (a minha|o meu)",
    re.IGNORECASE,
)
_CANDIDATO = re.compile(
    r"trabalhar (convosco|connosco|com v)|procuro (trabalho|emprego)|emprego|"
    r"\bvagas?\b|candidat|recrut|carreira|ser consultor|agente imobili|"
    r"fazer parte da (vossa|nossa)? ?equipa|^\W*trabalhar\W*$",
    re.IGNORECASE,
)
_MOTIVO_ESCALADA = re.compile(r"recrut|angaria|avalia|vend", re.IGNORECASE)


def _pagina(consulta) -> list[dict]:
    linhas: list[dict] = []
    inicio = 0
    while True:
        lote = consulta.range(inicio, inicio + _PAGINA - 1).execute().data
        linhas += lote
        if len(lote) < _PAGINA:
            return linhas
        inicio += _PAGINA


def _texto(msg: dict) -> str:
    c = msg.get("content")
    if isinstance(c, list):
        return " ".join(b.get("text") or "" for b in c if isinstance(b, dict))
    return str(c or "")


def _mensagens_do_utilizador(conversa: dict) -> list[str]:
    return [_texto(m) for m in (conversa.get("mensagens") or []) if m.get("role") == "user"]


def _primeiro_sinal(msgs: list[str]) -> tuple[str, int, str] | None:
    """(`vendedor`|`candidato`, índice da mensagem, texto) da 1.ª mensagem com sinal."""
    for i, texto in enumerate(msgs):
        if _VENDEDOR.search(texto):
            return "vendedor", i, texto
        if _CANDIDATO.search(texto):
            return "candidato", i, texto
    return None


def _destino_certo(tipo: str) -> str:
    return A4 if tipo == "vendedor" else A3


def _ja_existia(tipo: str, criado_em: str) -> bool:
    desde = _A4_DESDE if tipo == "vendedor" else _A3_DESDE
    return str(criado_em)[:10] >= desde


def _por_resolver(tipo: str, texto: str) -> bool:
    """O router de hoje, com esta mensagem, continuaria a não a mandar para o destino certo."""
    return route(texto, None) != _destino_certo(tipo)


def _linha(conversa: dict, tipo: str, indice: int, texto: str, mostrar_texto: bool) -> str:
    atual = conversa.get("agente")
    hoje = route(texto, None)  # o que o router de hoje faria com esta mensagem, sozinha
    resolvido = "router de hoje já resolveria" if hoje == _destino_certo(tipo) else f"router de hoje: {_NOME.get(hoje)}"
    base = (
        f"  {conversa['id'][:8]} {conversa['canal']:8} {str(conversa['criado_em'])[:10]} "
        f"{_NOME.get(atual):12} {tipo:9} msg {indice + 1}/{len(_mensagens_do_utilizador(conversa))} — {resolvido}"
    )
    return base + (f"\n      {texto[:90]!r}" if mostrar_texto else "")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dias", type=int, default=90, help="janela em dias (por omissão 90)")
    ap.add_argument("--texto", action="store_true", help="mostra 90 caracteres da mensagem com sinal (PII)")
    args = ap.parse_args()

    sb = get_supabase()
    desde = (datetime.now(timezone.utc) - timedelta(days=args.dias)).isoformat()
    conversas = _pagina(
        sb.table("agente_conversas").select("id,canal,agente,criado_em,mensagens").gte("criado_em", desde)
    )
    escaladas: dict[str, list[str]] = {}
    for t in _pagina(sb.table("agente_tarefas").select("conversa_id,motivo").eq("tipo", "escalar").not_.is_("conversa_id", "null")):
        escaladas.setdefault(t["conversa_id"], []).append(t.get("motivo") or "")

    print(f"Janela: {args.dias} dias | {len(conversas)} conversas")
    print("Por agente:", {_NOME.get(a): n for a, n in Counter(c.get("agente") for c in conversas).most_common()})

    # 1. Na Matilde com sinal de vendedor/candidato
    a1_depois, a1_antes = [], []
    for c in conversas:
        if c.get("agente") != A1:
            continue
        sinal = _primeiro_sinal(_mensagens_do_utilizador(c))
        if sinal:
            (a1_depois if _ja_existia(sinal[0], c["criado_em"]) else a1_antes).append((c, *sinal))
    pendentes_a1 = sum(_por_resolver(tipo, texto) for _, tipo, _, texto in a1_depois)
    print(f"\n[1] Na Matilde (A1) com sinal de vendedor/candidato, DEPOIS de A4/A3 existirem: {len(a1_depois)}")
    for c, tipo, i, texto in a1_depois:
        print(_linha(c, tipo, i, texto, args.texto))
    print(f"    (e {len(a1_antes)} anteriores à Bárbara/Inês, que não contam como desvio)")

    # 2. Na Maria e escaladas por motivo que tinha assistente própria
    a2_escaladas = []
    pendentes_a2 = 0
    for c in conversas:
        if c.get("agente") != A2:
            continue
        motivos = [m for m in escaladas.get(c["id"], []) if _MOTIVO_ESCALADA.search(m)]
        if motivos:
            a2_escaladas.append((c, motivos))
    print(f"\n[2] Na Maria (A2) e escaladas por recrutamento/angariação/avaliação/venda: {len(a2_escaladas)}")
    for c, motivos in a2_escaladas:
        msgs = _mensagens_do_utilizador(c)
        sinal = _primeiro_sinal(msgs)
        tipo = sinal[0] if sinal else ("candidato" if re.search("recrut", " ".join(motivos), re.I) else "vendedor")
        indice, texto = (sinal[1], sinal[2]) if sinal else (len(msgs) - 1, msgs[-1] if msgs else "")
        pendentes_a2 += _por_resolver(tipo, texto)
        print(_linha(c, tipo, indice, texto, args.texto) + f" | motivos: {sorted(set(motivos))}")

    # 3. Na Maria com mensagens que o router de hoje já encaminharia
    ja_corrigidos = []
    for c in conversas:
        if c.get("agente") != A2:
            continue
        for i, texto in enumerate(_mensagens_do_utilizador(c)):
            if route(texto, A2) != A2:
                ja_corrigidos.append((c, i, texto))
                break
    print(f"\n[3] Na Maria (A2) com mensagens que o router de hoje já encaminharia (resolvido pelas regex): {len(ja_corrigidos)}")
    for c, i, texto in ja_corrigidos:
        print(f"  {c['id'][:8]} {c['canal']:8} {str(c['criado_em'])[:10]} msg {i + 1} → {_NOME.get(route(texto, A2))}"
              + (f"\n      {texto[:90]!r}" if args.texto else ""))

    total = pendentes_a1 + pendentes_a2
    print(f"\nPOR RESOLVER (o router de hoje continuaria a falhar): {total}  ([1]: {pendentes_a1}, [2]: {pendentes_a2})")
    print("As linhas com 'router de hoje já resolveria' foram corrigidas pelas regex e não contam.")
    print("Se ficar a 0 com tráfego a sério (campanhas activas), o encaminhamento pelo modelo não se justifica.")
    print("Se aparecerem, reabrir docs/fases/encaminhamento-pelo-modelo-plano.md (decisões 1-4).")


if __name__ == "__main__":
    main()
