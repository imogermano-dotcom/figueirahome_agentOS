# Planeamento das Fases — Guia de Trabalho

> Este ficheiro diz ao Claude Code **como** conduzir o planeamento e implementação das fases seguintes, sem ser preciso planear noutro sítio. Lê isto sempre que fores começar uma fase nova.

---

## Princípio geral

Cada fase segue sempre o mesmo ciclo de 4 passos:

```
1. PLANEAR   →  2. VALIDAR  →  3. IMPLEMENTAR  →  4. FECHAR
```

Nunca saltar para a implementação sem o plano estar validado pelo utilizador.

---

## Passo 1 — PLANEAR

Antes de escrever código, produz um **plano da fase** e mostra-o ao utilizador. O plano deve conter:

- **Objectivo da fase** — o que fica a funcionar no fim, numa frase.
- **Tarefas** — lista ordenada e granular (cada tarefa = uma unidade de trabalho clara).
- **Ficheiros a criar/alterar** — caminhos concretos.
- **Dependências novas** — bibliotecas a instalar, com justificação.
- **Decisões em aberto** — perguntas que precisas que o utilizador responda antes de avançar.
- **Como testar** — como o utilizador valida que a fase funciona.

Escreve este plano em `docs/fases/faseN-plano.md` (ex: `docs/fases/fase2-plano.md`).

## Passo 2 — VALIDAR

- Apresenta o plano ao utilizador e **espera aprovação**.
- Resolve as "decisões em aberto" com ele antes de continuar.
- Se ele pedir alterações, actualiza o ficheiro do plano e volta a apresentar.

## Passo 3 — IMPLEMENTAR

- Segue o plano aprovado, tarefa a tarefa.
- Marca cada tarefa como concluída à medida que avanças.
- Se descobrires algo que obrigue a desviar do plano, pára e avisa o utilizador antes.
- Respeita as convenções de código do `CLAUDE.md`.
- Usa sempre placeholders para credenciais.

## Passo 4 — FECHAR

- Actualiza a checklist do "Estado actual" no `CLAUDE.md`.
- Escreve um resumo curto do que ficou feito em `docs/fases/faseN-resumo.md`.
- Diz ao utilizador como testar.
- Só então propõe avançar para a fase seguinte.

---

## Conteúdo previsto de cada fase

> Detalhe completo no `docs/PRD.md` e `docs/api-spec.md`. Resumo do âmbito:

### Fase 2 — Agente de Voz
Webhook Telnyx, streaming WebSocket de áudio, STT com Whisper (PT), Claude API com a persona da config, TTS Telnyx (PT-PT), e gravação dos dados da chamada (cliente + lead + transcrição + resumo) no Supabase.
**Decisões a levantar com o utilizador:** voz TTS específica da Telnyx; quanto confirmar verbalmente os dados; o que fazer se não perceber o cliente; horário de funcionamento.

### Fase 3 — Agente Broker
Endpoint de chat com Claude API + tool calling para consultar a base de dados; interface de chat no painel; depois canais WhatsApp, Telegram, email.
**Decisões a levantar:** que perguntas são prioritárias; formato das respostas; que canal integrar primeiro.

### Fase 4 — Painel Admin
Dashboard com métricas, gestão de clientes/imóveis/leads (tabelas, filtros, edição), editor de persona dos agentes, histórico de chamadas com transcrições, import CSV de imóveis.
**Decisões a levantar:** prioridade das secções; campos a mostrar em cada tabela.

### Fase 5 — Futuro
Idioma Inglês, integração com portais (Idealista, Imovirtual), relatórios, app mobile.

---

## Como o utilizador arranca uma fase

O utilizador vai dizer algo como:
> "Começa a Fase 2."

A tua resposta deve ser **sempre** o Passo 1 (PLANEAR) — nunca código directo. Só depois de validado é que implementas.

---

## Regra de ouro

Uma fase de cada vez. Plano antes de código. Validação antes de avançar. Checklist sempre actualizada.
