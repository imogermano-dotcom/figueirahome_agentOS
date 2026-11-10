"""Aviso ao corretor quando acontece algo que não pode esperar pelo painel.

Antes disto, uma lead qualificada e um escalamento acabavam ambos numa linha em
`agente_tarefas` e mais nada — se ninguém abrisse o painel, a lead paga que
qualificou às 23h ficava lá até alguém reparar. Uma lead imobiliária é
perecível; a tarefa continua a ser o registo, isto é o toque no ombro.

**Resend, não Microsoft Graph** (revisto 2026-08-31 — ver docs/decisoes.md). O
Graph chegou a ser configurado mas nunca teve credenciais em produção; Resend
é mais simples (API key estática, sem OAuth) para o mesmo caso de uso.

Duas decisões que se mantêm de antes:

* **Uma só função pública.** Trocar de canal — já aconteceu uma vez — mexe
  aqui e em mais lado nenhum. Os dois sítios que notificam não sabem do canal.
* **Síncrona e nunca levanta.** Ambos os chamadores já correm dentro de
  executores; falhar a enviar um aviso não pode derrubar uma conversa nem
  impedir a tarefa de ser criada — a tarefa é a rede de segurança do email.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # o envio não pode prender o turno; falhar depressa e seguir


def destinatarios() -> list[str]:
    """Quem recebe sempre — o director comercial. A consultora do imóvel entra
    por cima, resolvida a cada aviso (`_consultor_do_imovel`)."""
    return [e.strip() for e in settings.notificacoes_para.split(",") if e.strip()]


def _consultor_do_imovel(imovel_ref: str) -> tuple[str | None, str]:
    """Email de quem angariou o imóvel, e o motivo quando não há.

    Duas queries sem join porque `profiles` não tem FK para `imoveis` — a
    ponte é `profiles.ego_responsavel`, que guarda o nome tal como o eGO o
    escreve. Até 13/09 eram também dois *projectos* Supabase distintos
    (`imoveis` num, `profiles` no de Auth); o de Auth foi eliminado e
    `profiles` integrado no mesmo projecto — continua a ser duas consultas,
    já não é a duas bases.

    A cobertura é parcial e **não é uma tarefa de configuração por fazer**: a
    2026-08-16, 21 dos 54 imóveis publicados (39%) estavam atribuídos a pessoas
    que já saíram da agência — Lina Galvão (14), Ana Daniel (5), Maria José Boia
    (2). Criar-lhes perfil seria errado; o que falta é reatribuir a carteira no
    eGO, e isso é trabalho de backoffice, não nosso.

    Por isso o motivo devolvido é **neutro**. Uma mensagem a mandar "preencher o
    `profiles`" levaria alguém, daqui a uns meses, a criar contas a
    ex-colaboradoras a partir de um email automático.
    """
    from app.db.supabase_client import get_supabase

    try:
        im = (
            get_supabase().table("imoveis").select("angariador")
            .eq("imovel_ref", imovel_ref).limit(1).execute().data
        )
        if not im:
            return None, f"imóvel {imovel_ref} não existe na base"
        nome = (im[0].get("angariador") or "").strip()
        if not nome:
            return None, f"o imóvel {imovel_ref} não tem angariador no eGO"

        perfil = (
            get_supabase().table("profiles").select("email")
            .eq("ego_responsavel", nome).limit(1).execute().data
        )
        if not perfil or not perfil[0].get("email"):
            return None, (
                f"o imóvel {imovel_ref} está atribuído a {nome}, que não tem "
                "consultora activa associada — reatribuir no eGO"
            )
        return perfil[0]["email"], nome
    except Exception:
        logger.exception("Falha a resolver o consultor de %s", imovel_ref)
        return None, "erro a resolver o consultor (ver logs)"


def configurado() -> bool:
    """Sem API key ou sem destinatário, as notificações estão desligadas.

    Estado normal e não erro: permite ter isto em produção antes de existirem
    credenciais, e ligar sem novo deploy.
    """
    return bool(settings.resend_api_key and settings.resend_remetente and destinatarios())


def notificar(
    assunto: str, corpo: str, imovel_ref: str | None = None, para_extra: list[str] | None = None,
) -> None:
    """Manda o aviso. Engole tudo o que corra mal — ver docstring do módulo.

    Com `imovel_ref`, acrescenta a consultora que angariou esse imóvel aos
    destinatários. Sem ele, ou sem mapeamento, vai só ao director comercial — e
    o corpo diz porquê, para se ver que falta um dado em vez de parecer que o
    sistema ignorou alguém.
    """
    if not configurado():
        logger.debug("Notificações desligadas (sem API key do Resend ou destinatário).")
        return

    para = list(destinatarios())
    para += [e for e in (para_extra or []) if e not in para]
    if imovel_ref:
        email, motivo = _consultor_do_imovel(imovel_ref)
        if email:
            corpo += f"\n\nConsultor do imóvel {imovel_ref}: {motivo} <{email}>"
            if email not in para:  # o director pode ser o angariador
                para.append(email)
        else:
            corpo += f"\n\nSem consultor atribuído — {motivo}."

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_remetente,
                "to": para,
                "subject": assunto,
                "text": corpo,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Notificação enviada: %s", assunto)
    except httpx.HTTPStatusError as e:
        # O corpo do Resend diz o que falhou (domínio não verificado, remetente
        # inválido); sem ele o diagnóstico é adivinhar.
        logger.error(
            "Falha ao notificar (%s): HTTP %s — %s",
            assunto, e.response.status_code, e.response.text[:300],
        )
    except Exception:
        logger.exception("Falha ao notificar (%s) — a tarefa fica na mesma.", assunto)


def _alertas_extra() -> list[str]:
    return [e.strip() for e in settings.alertas_para.split(",") if e.strip()]


async def falha_de_sync(tipo: str, nome: str, origem: str, detalhe: str) -> None:
    """Falha de um sync do eGO: fica no `agente_sync_log` (tipo `<tipo>_erro`, que o painel não lista) e,
    se veio do cron (ninguém a olhar), manda email ao director e aos `alertas_para`. Uma falha manual já a
    vê quem carregou no botão. Nunca levanta. A falha de 14–15/10 (login do eGO) passou dois dias sem aviso.
    ponytail: só apanha o sync que corre e falha; um cron que nem arranca fica por detectar (verificar a
    idade do último sucesso num cron horário, se acontecer)."""
    import asyncio

    from app.db.supabase_client import get_supabase

    detalhe = (detalhe or "sem detalhe")[:500]
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: get_supabase().table("agente_sync_log").insert(
                {"tipo": f"{tipo}_erro", "resumo": {"erro": detalhe}, "origem": origem}
            ).execute(),
        )
    except Exception:
        logger.exception("Falha a registar o erro do sync %s", tipo)
    if origem != "cron":
        return
    try:
        await loop.run_in_executor(
            None,
            lambda: notificar(
                f"Sync falhou — {nome}",
                "\n".join((
                    f"O sync de {nome} (cron) falhou.",
                    "",
                    f"Erro: {detalhe}",
                    "",
                    "Os dados ficam desatualizados até o sync voltar a correr. Ver os logs de figueirahome-scraper "
                    "e figueirahome-agentos no Fly.",
                )),
                para_extra=_alertas_extra(),
            ),
        )
    except Exception:
        logger.exception("Falha a avisar do erro do sync %s", tipo)


def demo() -> None:
    """Auto-verificação das guardas. `python -m app.notificacoes` de `backend/`"""
    original = (settings.resend_api_key, settings.resend_remetente, settings.notificacoes_para)
    try:
        settings.resend_api_key = settings.resend_remetente = ""
        settings.notificacoes_para = ""
        assert configurado() is False
        notificar("x", "y")  # não pode levantar nem gerar tráfego

        settings.resend_api_key = "k"
        settings.resend_remetente = "avisos@exemplo.pt"
        assert configurado() is False, "sem destinatário continua desligado"

        settings.notificacoes_para = " a@b.pt ,, c@d.pt "
        assert destinatarios() == ["a@b.pt", "c@d.pt"], destinatarios()
        assert configurado() is True

        # Sem rede/chave real: tem de falhar em silêncio, não rebentar.
        notificar("teste", "corpo")
    finally:
        settings.resend_api_key, settings.resend_remetente, settings.notificacoes_para = original

    print("notificacoes OK")


if __name__ == "__main__":
    demo()


def falha_de_workflow(workflow: str, no: str, erro: str, execucao: str, dry: bool = False) -> dict:
    """Um fluxo do n8n falhou (o seu «Error Workflow» chama-nos). Email a `notificacoes_para` + `alertas_para`,
    no máximo UM por fluxo em 12 h (o vigia corre de 30 em 30 min); regista `n8n_falha` em `agente_sync_log`.
    O token da Meta expirou a 09/11 e o vigia e a entrada das leads ficaram um dia a falhar sem aviso.
    ponytail: o aviso sai do backend, por isso se o backend estiver em baixo não há email; n8n parado ou fluxo
    desligado também não se detetam (o Error Workflow só corre se o fluxo arrancar)."""
    from datetime import datetime, timedelta, timezone

    from app.db.supabase_client import get_supabase

    workflow, no, execucao = (workflow or "n8n")[:120], (no or "")[:120], (execucao or "")[:40]
    erro = (erro or "sem detalhe").strip()[:500]
    sb = get_supabase()
    desde = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    recentes = (sb.table("agente_sync_log").select("resumo").eq("tipo", "n8n_falha")
                .gte("executado_em", desde).limit(200).execute().data or [])
    if any((r.get("resumo") or {}).get("workflow") == workflow for r in recentes):
        return {"avisou": False, "repetido": True}
    if dry:
        return {"avisou": False, "dry": True}
    linhas = [f"O fluxo «{workflow}» (n8n) falhou" + (f" no nó «{no}»" if no else "") + ".", "", f"Erro: {erro}"]
    if execucao:
        linhas.append(f"Execução n8n: {execucao}")
    if "oauth" in erro.lower() or "facebook" in erro.lower() or "190" in erro:
        linhas += ["", "Parece o token da Meta/Facebook: a credencial «Facebook Figueira Home» (n8n) é partilhada pelo vigia "
                   "e pelo «Meta leads to supabase», que lê cada lead com ela. Com o token morto, as leads novas podem não "
                   "estar a entrar. Ver também a ligação ao Facebook no Make."]
    linhas += ["", "Este aviso não se repete em 12 h para o mesmo fluxo."]
    notificar(f"n8n: o fluxo «{workflow}» falhou", "\n".join(linhas), para_extra=_alertas_extra())
    try:
        sb.table("agente_sync_log").insert({"tipo": "n8n_falha", "origem": "n8n",
                                            "resumo": {"workflow": workflow, "no": no, "erro": erro, "execucao": execucao}}).execute()
    except Exception:
        logger.exception("Falha a registar n8n_falha")
    return {"avisou": True}
