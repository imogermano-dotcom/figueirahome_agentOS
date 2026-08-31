# Handoff — 2026-08-30

> Sessão de teste do fluxo `01` em produção e diagnóstico do `03`. Sem código
> novo no backend — só validação end-to-end e dois ficheiros de documentação
> corrigidos. Continuação directa do handoff de 29/08
> (`incidente-whatsapp-mudo-2026-08-29.md`, `contacto-humano-resumo.md`).

## O que foi implementado / verificado

**Nada de código foi alterado.** O trabalho foi todo de teste e documentação:

1. **`01` validado ponta a ponta em produção**, duas vezes:
   - Lead de teste `teste-manual-001` (`meta_lead_id`), ref normal `FH2581`,
     número real do utilizador. `POST /webhook/lead-nova` → `template_enviado_em`
     gravado, texto renderizado certo, mensagem chegou a sério ao WhatsApp. O
     utilizador respondeu ("Sim quero mais informações") e o A1 (`a1_vendedor`)
     respondeu com a ficha certa do imóvel **e** aplicou a guarda de orçamento
     (300.000€ registados, imóvel acima do preço) — pipeline `n8n → Meta →
     webhook → A1` confirmado saudável.
   - Lead de teste `teste-manual-002`, ref **com espaço** `FH2460 3C` (uma das
     11/54 referências problemáticas). Primeira tentativa deu `500 Error in
     workflow` — mas o fluxo activo no n8n **ainda não tinha as alterações
     publicadas**, portanto não prova nada. Repetido depois de publicar:
     `200 OK`, `template_enviado` com ref e resumo correctos
     (`FH2460 3C — Apartamentos novos na Quinta de Santa Maria`), mensagem
     chegou. **O nó nativo do Supabase lida bem com o espaço** — o bug do
     `encodeURIComponent` temido desde a troca de HTTP Request para nó nativo
     **não se confirmou**. Fechado.

2. **Envio no `01` confirmado como nó nativo WhatsApp Business Cloud**, não
   HTTP Request — o utilizador corrigiu um detalhe que faltava no README (o
   ficheiro de referência `01-enviar-template.json` no repo ainda mostra
   `httpRequest` nesse nó; ficou marcado como desactualizado).

3. **Bug novo, real, encontrado no `03`**: o nó *Ler leads pendentes* filtra
   por `template_enviado_em=lt.{{ $now.minus(48,'hours').toISO() }}`. O
   `.toISO()` do Luxon dá o offset **local** (`+02:00`); esse `+`, ao ir por
   query string no `filterString`, é lido como espaço. PostgREST recebia
   literalmente `"2026-08-27T18:59:51.223 02:00"` e rejeitava com
   `invalid input syntax for type timestamp with time zone`. **Fix**: trocar
   por `.toUTC().toISO()` — sai com `Z`, sem `+`, sem o problema. Documentado
   no README; **por aplicar no nó do n8n e por reconfirmar**.

4. **Descoberta durante o teste do `03`**: a consulta apanhou leads de
   18-19/08. Correcto pela query (`respondeu_em is.null`, `follow_up_em
   is.null`, `estado in (nova,contactada)`, sem chão de data) — mas **decisão
   em aberto**: o `03` não tem o `criado_em gte.<data>` que o `02` tem
   (README linha ~347). Sem chão, a primeira corrida vai tentar todo o
   backlog elegível desde sempre, incluindo o buraco dos 6 dias mudos
   (24-29/08). **Por decidir com o utilizador**: deixar correr o backlog
   todo (é a medição que valida ou mata a hipótese das 48h, já prevista no
   README) ou pôr uma janela para não sobrepor com o reenvio manual das 45
   leads (prazo 23/09).

## Ficheiros principais modificados

- `docs/n8n/README.md` — três correcções:
  - Nó *Ler imóvel* do `01`/`02`: bug do espaço na ref marcado como
    **verificado, não é bug** (antes dizia "por verificar").
  - Envio do `01`: nota de que é nó nativo WhatsApp Business Cloud, e que o
    `.json` de referência no repo está desactualizado nesse nó.
  - Consulta do `03`: `.toISO()` → `.toUTC().toISO()`, com a explicação do
    bug do `+`/espaço.
- `CLAUDE.md` — bug do `encodeURIComponent` removido de "Bugs conhecidos"
  (falso alarme); passo 0 dos "Próximos passos" actualizado para reflectir o
  teste feito.
- **Nenhum ficheiro de `backend/` tocado.**

## Decisões arquitecturais

Nenhuma nova. Esta sessão foi verificação, não desenho.

## Bugs conhecidos — mudanças

- ✅ **Fechado**: `Ler imóvel` do `01`/`02` partir em refs com espaço
  (`FH2460 3C`). Nó nativo lida bem, testado em produção 29/08.
- 🆕 **Novo, com fix documentado mas não aplicado**: timestamp com offset
  local (`+02:00`) no `filterString` do `03` vira espaço em vez de `+` —
  PostgREST rejeita. Fix: `.toUTC().toISO()` no nó *Ler leads pendentes*.
- ⚠️ **Aberto**: falta decidir se o `03` precisa de um chão de data
  (`criado_em gte.<data>`) como o `02` tem, para não sobrepor com o reenvio
  manual das 45 leads.
- Os restantes bugs conhecidos (atraso de 12h do `01`, falta de
  `logging.basicConfig`, `agente_leads` morta, dedup sob carga, agente de
  voz) **inalterados** — ver `CLAUDE.md`.

## Próximos passos

1. Aplicar o fix `.toUTC().toISO()` no nó *Ler leads pendentes* do `03` e
   publicar.
2. Decidir chão de data do `03` (ver ponto 4 acima) antes de correr com
   `Limit=5`.
3. Correr o `03` com `Limit=5`, trigger desligado, confirmar que os 5 ficaram
   `sem_resposta` com `follow_up_em` e os outros leads intactos (contagem de
   controlo no `docs/n8n/README.md`).
4. Importar `02` (falta confirmar se já está testado — esta sessão só cobriu
   `01` e o diagnóstico do `03`).
5. Duas leads de teste ficaram na BD por decisão do utilizador ("deixa estar
   por agora"): `teste-manual-001` (`FH2581`) e `teste-manual-002`
   (`FH2460 3C`), ambas com `estado='contactada'` e telefone real do
   utilizador. Limpar antes do reenvio das 45 leads reais, para não as
   confundir com dados de produção.
6. Continua tudo o que já estava nos "Próximos passos" do `CLAUDE.md`
   (reenvio das 45, "Validar CRM", campos reais do formulário de venda, etc.)
   — nada disso mudou hoje.
