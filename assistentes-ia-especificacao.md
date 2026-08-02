# Assistentes IA — Agência Imobiliária

> **Documento de Especificação & Arquitectura**
> Versão 1.0 | Junho 2026
> Fonte: `assistentes_ia_v11b.docx` — convertido para uso em planeamento com Claude Code.

---

## Visão Geral dos Assistentes

| ID | Assistente | Função |
|----|-----------|--------|
| **A1** | 🏠 Assistente Vendedor | Qualifica clientes compradores, informa sobre imóveis e marca visitas |
| **A2** | 📞 Atendimento Geral | Recepciona e encaminha todas as questões gerais da agência |
| **A3** | 👤 Assistente de Recrutamento | Responde a candidatos e qualifica leads de consultores imobiliários |
| **A4** | 🔑 Assistente Angariador | Qualifica proprietários com interesse em angariar o seu imóvel |

---

## 1. Introdução e Objectivos

Este documento define a arquitectura e especificações dos quatro assistentes de inteligência artificial para a agência imobiliária. O objectivo é criar um sistema de atendimento automatizado, disponível 24/7, capaz de qualificar leads, responder a questões e encaminhar contactos — operando de forma consistente em quatro canais distintos.

> 📌 Os assistentes **não substituem os consultores**: são uma camada de primeiro contacto que qualifica, informa e encaminha, libertando a equipa para negociações e relações de valor.

### 1.1 Princípios Orientadores

- **Resposta imediata** — nenhum lead fica sem resposta em menos de 2 minutos
- **Qualificação antes de escalar** — o assistente recolhe o máximo de contexto antes de passar a um humano
- **Tom profissional e caloroso** — linguagem clara, sem jargão excessivo
- **Escalada inteligente** — reconhece quando deve envolver um consultor e faz a transição de forma fluida
- **Omnicanal consistente** — a mesma qualidade de resposta em WhatsApp, Email, SMS e Voz

### 1.2 Canais Suportados

| Canal | Características Principais |
|-------|---------------------------|
| **WhatsApp Business** | Mensagens ricas (imagens, PDFs, botões). Canal preferencial em Portugal. Limite de 4096 caracteres por mensagem. |
| **Email** | Respostas estruturadas em HTML. Permite envio de fichas de imóveis e documentos. Sem limite de caracteres. |
| **SMS** | Mensagens curtas (máx. 160 caracteres por SMS). Apenas texto. Ideal para lembretes e confirmações. |
| **Voz (Voice)** | Interacção por voz via IVR ou agente de voz. Requer síntese de voz (TTS) e reconhecimento (STT). Respostas mais curtas e directas. |

---

## 2. Arquitectura Geral do Sistema

A arquitectura segue um modelo de três camadas: **Recepção de Mensagem → Processamento IA → Resposta & Registo**. Todos os dados são persistidos numa base de dados Supabase.

### 2.1 Diagrama de Fluxo

```
CLIENTE ▶ [WhatsApp] [Email] [SMS] [Voz] [Instagram] [Facebook]
                              ▼
              PLATAFORMA DE AUTOMAÇÃO (Make / n8n)
                              ▼
       ROUTER DE INTENÇÃO — identifica qual assistente responde
                              ▼
   ┌──────────────┬─────────────┬──────────────────┬─────────────────┐
   │ A1 Vendedor  │  A2 Geral   │ A3 Recrutamento  │ A4 Angariador   │
   └──────────────┴─────────────┴──────────────────┴─────────────────┘
                              ▼
       CLAUDE AI (API Anthropic) — Motor de Linguagem Natural
                              ▼
              SUPABASE — Base de Dados Central
                              ▼
   ┌────────────────────────────────┬──────────────────────────────────┐
   │ ✅ SIM — Escalar Humano         │ 🤖 NÃO — Resposta IA             │
   │ Notifica consultor via          │ Envia resposta ao cliente e      │
   │ WhatsApp/Email com contexto     │ regista conversa na BD Supabase  │
   │ completo da conversa            │                                  │
   └────────────────────────────────┴──────────────────────────────────┘
```

### 2.2 Roteamento de Intenção (Router)

O roteamento funciona em **dois níveis**: primeiro identifica qual dos quatro assistentes responde; depois, dentro do A1 (Comprador), um sub-router afina a intenção específica do cliente.

Sinais usados no roteamento:

- O **canal de entrada** (número/email dedicado por função determina o assistente directamente)
- As **primeiras palavras da mensagem** — palavras-chave de nível 1 para escolha do assistente
- O **histórico de conversação anterior** (thread activo com contexto já definido)
- A **hora do contacto** (fora de horas → A2 recolhe dados e promete follow-up)

#### Nível 1 — Escolha do Assistente

| Trigger / Sinal | Assistente Atribuído | Lógica |
|-----------------|---------------------|--------|
| "quero comprar", "procuro casa", "tenho interesse", "quanto custa", referência de imóvel | **A1 — Vendedor** | Intenção de compra, arrendamento ou interesse em imóvel específico |
| "quanto vale a minha casa", "quero vender", "penso vender", "avaliação", "avaliar o meu imóvel" | **A4 — Angariador** | Proprietário com intenção de vender ou obter avaliação do seu imóvel |
| "quero trabalhar", "consultor imobiliário", "recrutamento", "candidatura" | **A3 — Recrutamento** | Interesse em carreira na agência |
| Qualquer outra mensagem / não classificada | **A2 — Geral** | Fallback — recolhe contexto e redirige |
| Número de WhatsApp dedicado por função | Assistente da função | Roteamento directo por configuração de número |

#### Nível 2 — Sub-roteamento dentro do A1 (Comprador)

Após identificar que o cliente é comprador/arrendatário, o assistente detecta a sub-intenção imediata para adaptar o fluxo:

| Código | Sub-intenção | Exemplos de Trigger | Próxima Acção do A1 |
|--------|-------------|--------------------|--------------------|
| **SI** | Saber Informações | **SI-A**: referência ou morada conhecida ("FH 2233", "Rua Almeida Garrett") → resposta directa sem qualificação. **SI-B**: critérios genéricos ("T2", "moradia", "até 300k") → qualificação primeiro | SI-A: lookup directo por ref/morada → ficha completa imediata. SI-B: qualifica critérios → filtra BD → apresenta até 3 opções |
| **SV** | Visitar Imóvel | "Quero visitar", "Posso ver", "Quando posso ir ver?", "Agendar visita" | Verifica disponibilidade de agenda e propõe 2-3 datas/horas para visita |
| **SC** | Simular Crédito | "Quanto fico a pagar?", "Consigo crédito?", "Simulação", "Prestação mensal" | Apresenta simulação indicativa (prestação, taxa) e oferece contacto com parceiro de crédito |
| **FP** | Fazer Proposta | "Quero fazer oferta", "Posso propor", "Estou interessado em comprar" | Escala imediatamente para consultor com contexto completo da conversa |

> 💡 Se a sub-intenção não for clara nas primeiras 2 mensagens, o A1 pergunta directamente: *"Posso ajudá-lo a saber mais sobre o imóvel, agendar uma visita, simular o crédito ou fazer uma proposta?"*

### 2.3 Motor de IA — Claude API (Anthropic)

Recomenda-se a utilização da API da Anthropic (modelos Claude) como motor de geração de linguagem natural. Justificação:

- Suporte nativo a instruções em **português europeu**
- Capacidade de seguir **system prompts complexos** e respeitar restrições
- **Contexto longo** (até 200K tokens) — permite incluir fichas de imóveis completas no contexto
- Fácil **integração via HTTP REST** com qualquer plataforma de automação

#### Configuração por Assistente

| Parâmetro | Valor Recomendado |
|-----------|------------------|
| **Modelo** | `claude-sonnet-4-5` (equilíbrio custo/qualidade) ou `claude-opus-4` para voz |
| **Temperature** | 0.3 — 0.5 (respostas consistentes, mas não robóticas) |
| **Max tokens resposta** | WhatsApp: 400 \| Email: sem limite \| SMS: 120 \| Voz: 200 |
| **System prompt** | Um por assistente (ver §3–6) |
| **Memória de conversação** | Últimas 10 mensagens do thread no contexto |
| **Língua** | Português Europeu (PT-PT) |

### 2.4 Plataforma de Automação — Recomendação

| Critério | Make (Integromat) | n8n (Self-hosted) |
|----------|------------------|-------------------|
| **Custo** | Pago por operação (~9-29€/mês) | Gratuito (infraestrutura própria) |
| **Facilidade de configuração** | Alta — interface visual intuitiva | Média — requer servidor VPS |
| **Integrações nativas** | Mais de 1.500 apps nativas | 900+ (crescendo rapidamente) |
| **WhatsApp Business** | Integração nativa disponível | Via HTTP ou conector específico |
| **Controlo de dados** | Dados passam pelos servidores Make | 100% nos seus servidores |
| **Escalabilidade** | Limitada pelo plano contratado | Ilimitada — apenas hardware |
| **Manutenção** | Zero (SaaS) | Requer gestão do servidor |
| **Ideal para** | Início rápido, equipa não técnica | Controlo total, volumes altos |

> ✅ **Recomendação:** Começar com **Make** para arrancar rapidamente e migrar para **n8n self-hosted** quando o volume de mensagens justificar o custo (geralmente acima de 5.000 operações/mês).

### 2.5 Base de Conhecimento — Supabase

O projecto Supabase já existente (**EGO Scrapper — `zphasvfopnbzwnaidsnw.supabase.co`**) contém dados sincronizados do CRM eGO. O developer deve usar este projecto como base, criando apenas as tabelas adicionais necessárias para os assistentes.

#### Tabelas Já Existentes — Usar Directamente

> ✅ Estas tabelas **já existem e têm dados reais**. O assistente deve consultá-las via API Supabase — **não recriar**.

| Tabela existente | O que contém e como o assistente a usa |
|-----------------|---------------------------------------|
| **`imoveis`** (178 registos) | Tabela principal de imóveis. Campos: `imovel_ref`, `natureza`, `titulo`, `quartos`, `casas_banho`, `area_util`, `venda_preco`, `arrendamento_preco`, `morada`, `concelho`, `freguesia`, `zona`, `disponibilidade`, `conservacao`, `descricao`, `foto_principal`, `fotos` (JSONB). Features booleanas: `piscina`, `garagem`, `jardim`, `terraco`, `varanda`, `vista_mar`, `vista_praia`, `ar_condicionado`, `elevador`. O A1 filtra esta tabela para responder a questões SI. |
| **`contactos`** (16.900 registos) | Base de contactos do CRM. Campos: `nome`, `telefone`, `telemovel`, `email`, `tipos`, `responsavel`. Campos RGPD por canal (`rgpd_telefone`, `rgpd_telemovel`, `rgpd_email`) e `whatsapp_permissao`. O assistente deve verificar se o contacto já existe antes de criar um novo. |
| **`oportunidades`** (24.500+ registos) | Pipeline CRM de oportunidades. Preferências do comprador: `pref_tipologia`, `pref_orcamento_max`, `pref_zona`, `pref_outros`. Campos de visita: `visita_imovel_ref`, `visita_data`, `visita_cliente`, `visita_responsavel`. O assistente escreve nesta tabela quando qualifica um novo lead ou regista uma visita. |
| **`tarefas`** (12.100 registos) | Tarefas associadas a oportunidades. O assistente pode criar uma tarefa de follow-up quando escala para um consultor. |

#### Tabelas a Criar — Sugestão para o Developer

> 🔧 Estas tabelas **não existem ainda**. O developer deve criá-las no mesmo projecto Supabase.

| Tabela nova sugerida | Estrutura recomendada e propósito |
|---------------------|----------------------------------|
| **`ai_conversations`** | `id`, `channel` (whatsapp/email/sms/voice), `assistant_type` (A1/A2/A3/A4), `contact_phone`, `contact_email`, `started_at`, `status` (active/closed/escalated), `escalated_to` (nome do consultor). Regista cada sessão de conversa iniciada pelo assistente. |
| **`ai_messages`** | `id`, `conversation_id` (FK `ai_conversations`), `role` (user/assistant), `content` (text), `created_at`. Armazena o histórico de mensagens para contexto da IA (últimas 10 por conversa). |
| **`ai_visit_bookings`** | `id`, `conversation_id` (FK `ai_conversations`), `imovel_ref` (FK `imoveis`), `contact_name`, `contact_phone`, `scheduled_at` (timestamp), `consultant_name`, `status` (pending/confirmed/cancelled), `notes`. Marcações de visita criadas pelo A1 (fluxo SV). |
| **`agency_knowledge`** | `id`, `key` (text, único), `value` (text), `categoria` (faq/horario/servico/recrutamento/angariacao). Tabela de configuração estática: horários, serviços, FAQs, condições de recrutamento. Editável pela agência sem tocar no código. |

> 💡 **Sugestão ao developer:** a tabela `oportunidades` já tem campos de preferências de comprador (`pref_tipologia`, `pref_orcamento_max`, `pref_zona`). Quando o A1 qualifica um comprador, deve criar uma oportunidade do tipo "Venda" ou "Arrendamento" nesta tabela, preenchendo esses campos — assim o lead fica logo no CRM sem duplicação.

#### Query de Exemplo — Pesquisa de Imóveis (A1 / Sub-intenção SI)

```sql
SELECT imovel_ref, natureza, titulo, quartos, casas_banho, area_util,
       venda_preco, arrendamento_preco, morada, concelho, freguesia, zona,
       piscina, garagem, vista_mar, terraco, descricao, foto_principal
FROM imoveis
WHERE disponibilidade = 'Disponível'
  AND (quartos = :quartos OR :quartos IS NULL)
  AND (venda_preco <= :preco_max OR :preco_max IS NULL)
  AND (concelho ILIKE :zona OR freguesia ILIKE :zona OR zona ILIKE :zona OR :zona IS NULL)
ORDER BY venda_preco ASC
LIMIT 3;
```

#### Segurança — Nota para o Developer

- Os assistentes acedem via **service role key** — apenas no servidor, nunca exposta no cliente ou em logs
- Activar **Row Level Security** em todas as tabelas novas criadas
- ⚠️ **ATENÇÃO:** a tabela `feedback_queries` tem RLS **desactivado** — qualquer pessoa com a chave anon pode ler e escrever. Activar com:
  ```sql
  ALTER TABLE public.feedback_queries ENABLE ROW LEVEL SECURITY;
  ```
- Dados pessoais (RGPD): usar **soft delete** (campo `deleted_at`) — nunca apagar registos de conversas
- Logs de mensagens são **write-once** — não permitir UPDATE nem DELETE via políticas RLS

### 2.6 Fontes de Entrada e Triggers

| Fonte de Entrada | Comportamento |
|-----------------|---------------|
| **Entrada manual** — cliente contacta por iniciativa própria (WhatsApp, Instagram, Facebook, Email, SMS, Voz) | Passa pelo router de intenção (§2.2) que analisa a mensagem e determina qual assistente responde. |
| **Campanha Meta Lead Ads** — lead capturado num anúncio Facebook/Instagram onde o cliente aceitou ser contactado | **Bypassa o router.** A plataforma de automação recebe o webhook da Meta com nome, telefone e `campanha_id`, e activa directamente o assistente mapeado à campanha. O assistente inicia a qualificação de imediato. |

> 📣 **Mapeamento de campanhas Meta → Assistente:**
> - Campanhas de Compra / Venda de imóveis → **A1** (Assistente Vendedor)
> - Campanhas de Angariação / "Quer vender a sua casa?" → **A4** (Assistente Angariador)
> - Campanhas de Recrutamento / "Trabalhe connosco" → **A3** (Assistente de Recrutamento)
> - Campanhas institucionais ou genéricas → **A2** (Atendimento Geral)

**Fluxo técnico Meta Lead Ads:**

| Etapa | Detalhe técnico |
|-------|----------------|
| **1. Lead submetido no anúncio Meta** | Cliente preenche formulário no Facebook/Instagram Ad e aceita ser contactado via WhatsApp. Consentimento RGPD coberto pelo Lead Form. |
| **2. Webhook Meta → Make/n8n** | Make/n8n recebe instantaneamente: nome, telefone, email (se recolhido), `campanha_id`, `ad_id`. |
| **3. Mapeamento `campanha_id` → assistente** | Tabela de configuração em Supabase (ou variável no Make/n8n) associa cada `campanha_id` ao assistente correcto. |
| **4. Mensagem automática via WhatsApp** | O assistente envia a primeira mensagem em **menos de 2 minutos** após a submissão do lead. Exemplo: *"Olá [Nome], vi que se interessou pelo nosso anúncio. Sou o assistente virtual da [Agência] e estou aqui para o ajudar. Pode falar agora?"* |
| **5. Qualificação imediata** | Se o cliente responder, o assistente activa directamente o fluxo de qualificação do assistente mapeado (ex: SI-B do A1 para campanhas de compra). |
| **6. Registo na BD** | Lead criado em `ai_conversations` com `source: "meta_lead_ads"`, `campanha_id` e `ad_id` para rastreabilidade. |

> ⚠️ **Nota RGPD:** o consentimento do Lead Form Meta cobre o primeiro contacto via WhatsApp. O assistente deve mencionar o motivo do contacto no início da conversa e confirmar disponibilidade antes de avançar com a qualificação.

### 2.7 Deduplicação de Clientes — Regra Transversal

> **REGRA FUNDAMENTAL** — aplica-se a **TODOS** os assistentes (A1, A2, A3, A4) e a todos os tipos de cliente (comprador, vendedor, arrendatário, candidato): antes de criar qualquer registo na base de dados, **pesquisar SEMPRE primeiro. Nunca duplicar clientes.**

| Situação | Acção correcta | O que NÃO fazer |
|----------|---------------|----------------|
| **Novo contacto — cliente desconhecido** | Pesquisar na BD por telefone → email → nome. Se não encontrar → criar novo registo + oportunidade adequada. | Criar cliente sem pesquisar primeiro |
| **Cliente encontrado (mesmo número ou email)** | Usar o registo existente. Adicionar: nova oportunidade, nova nota com contexto da conversa, ou nova tarefa para o consultor. | Criar segundo registo — duplicado |
| **Cliente com dados parcialmente diferentes (ex: novo número)** | Usar registo existente, actualizar o campo em falta. Registar nota: "Contacto via [canal] — dados actualizados." | Criar novo cliente por mudança de número |
| **Comprador que tem também imóvel para vender** | Mesmo registo de cliente. Criar **duas oportunidades distintas** ligadas ao mesmo cliente: (1) oportunidade de compra + (2) oportunidade de angariação. | Criar dois clientes separados |
| **Arrendatário que quer comprar ou vender** | Mesmo registo. Adicionar nova oportunidade do tipo correspondente. | Criar novo cliente para a nova intenção |
| **Candidato a consultor (A3) que é também cliente** | Verificar se existe como cliente. Se sim, usar o mesmo registo e adicionar a informação de recrutamento como nota/processo separado. | Criar dois registos independentes |
| **Lead de campanha Meta** | Pesquisar antes de criar. Se já existir, adicionar a oportunidade da campanha ao registo existente com nota da origem (`campanha_id`). | Assumir que é sempre novo cliente por vir de campanha |

**Prioridade de pesquisa e normalização:**

| Campo | Prioridade | Regra de normalização |
|-------|-----------|----------------------|
| **Telefone** | 1º — mais fiável | Remover espaços e hífens; converter `+351`/`00351` para 9 dígitos nacionais |
| **Email** | 2º | Lowercase antes de comparar — `geral@email.com` = `GERAL@EMAIL.COM` |
| **Nome completo** | 3º — só confirmação | Não criar fusão automática — confirmar com o cliente em caso de dúvida |

Em caso de dúvida, **escalar para o consultor** antes de criar ou fundir registos.

---

## 3. A1 — Assistente Vendedor

> 🏠 **A1 — Assistente Vendedor:** Qualifica clientes compradores, informa sobre imóveis e marca visitas.

### 3.1 Objectivo

Ser o primeiro ponto de contacto para clientes que pretendem **comprar ou arrendar** um imóvel. O A1 distingue quatro sub-intenções e adapta o fluxo a cada uma — desde informação inicial até proposta de compra — sem intervenção humana, excepto no momento da proposta.

### 3.2 Fluxo por Sub-Intenção

#### SI — Saber Informações

Este fluxo divide-se em dois caminhos consoante o cliente já identifique ou não o imóvel:

> 📌 **Detecção automática:** se a mensagem contém uma **referência** (ex: "FH 2233", "FH2233") ou uma **morada/rua reconhecível** → caminho **SI-A** directo. Se contém **tipologia ou critérios genéricos** ("T2", "moradia", "perto da praia") → caminho **SI-B** com qualificação.

##### SI-A — Imóvel Identificado (referência ou morada)

Exemplos: *"quero informações sobre o FH 2233"*, *"o apartamento da Rua Almeida Garrett"*, *"vi um imóvel no vosso site com a referência…"*

> ⚠️ **Princípio-chave:** o assistente **NÃO revela o preço imediatamente**. Primeiro faz uma qualificação contextual rápida (2 perguntas, num único bloco) baseada no que já sabe do imóvel — natureza e tipologia. Só depois, em função do orçamento declarado, adapta a resposta. Isto evita que o cliente se desligue antes de perceber o valor real do imóvel.

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Lookup silencioso** | Pesquisa na BD por `imovel_ref` ou morada. Obtém internamente: natureza, tipologia, preço, zona. **Não revela ainda.** | `imovel_ref`, preço, natureza |
| **2. Qualificação contextual** | Confirma interesse com base no que sabe: *"Encontrei a [natureza] em [zona]. Para o ajudar melhor — é este tipo de imóvel que procura nesta zona? E qual o montante que tenciona investir?"* Máximo **2 perguntas num só bloco**. | Tipologia confirmada, orçamento |
| **3a. Orçamento compatível** | Apresenta ficha completa: preço, área, características, descrição, foto. Tom: valoriza o imóvel. | Ficha apresentada |
| **3b. Orçamento abaixo do preço** | **Não rejeita** — reencaminha: *"Este imóvel tem um valor de [X€], que está acima do orçamento que indicou. No entanto, temos outras [natureza]s com características semelhantes que se encaixam melhor no que procura. Quer que pesquise?"* → activa **SI-B** com critérios já recolhidos. | Critérios para SI-B |
| **3c. Orçamento não declarado** | Apresenta ficha mas anuncia o preço de forma contextualizada: *"Este imóvel tem características premium — [lista breve] — e está disponível por [X€]. Faz sentido para o que procura?"* | Reacção do cliente |
| **4. Conversão** | *"Quer agendar uma visita ou tem mais alguma dúvida sobre este imóvel?"* | Sub-intenção seguinte |
| **5. Cross-sell angariação** | No fecho natural da conversa pergunta: *"Só para completar o seu perfil — tem algum imóvel para vender ou arrendar?"* Se sim: identifica tipo e localização; pergunta se já está à venda; se sim, se está com agências ou apenas a nível particular. | Tipo/morada, estado (livre / c/ agência / particular) |
| **6. Registo duplo** | Cria **DUAS oportunidades** na BD em simultâneo: (1) Oportunidade de **compra** — com `imovel_ref`, orçamento declarado e perfil do comprador. (2) Oportunidade de **angariação** — com dados do imóvel do cliente, estado actual e flag para follow-up pelo A4. Transfere contexto de angariação para A4. | Oportunidade compra + Oportunidade angariação criadas |

> 💬 **Exemplo real:** cliente pergunta pelo imóvel da Rua Almeida Garrett (moradia €450k). Assistente responde: *"Encontrei a moradia na Rua Almeida Garrett! É uma moradia T4 com jardim e garagem, em zona muito procurada. Posso perguntar — é este tipo de moradia que procura nesta área? E qual o montante que tenciona investir?"* → Se cliente diz €200k: *"Esta moradia específica tem um valor acima desse orçamento, mas tenho outras moradias nesta zona com excelentes características que se encaixam melhor. Quer que pesquise?"*

##### SI-B — Pesquisa por Critérios (sem imóvel específico)

Exemplos: *"têm T2 na Figueira?"*, *"procuro moradia com piscina"*, *"o que têm até 300 mil euros?"*

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Qualificação** | Pergunta tipologia (se não mencionada), zona preferida e orçamento máximo. Máx. **2-3 perguntas num único bloco**. | Tipologia, zona, orçamento |
| **2. Pesquisa** | Filtra tabela `imoveis` com os critérios recolhidos. Ordena por preço crescente. | Critérios de pesquisa |
| **3. Apresentação** | Apresenta **até 3 imóveis** com ficha resumida (referência, tipologia, preço, zona, 1 frase da descrição). | Property IDs apresentados |
| **4. Interesse** | Pergunta qual desperta mais interesse ou se quer ver mais detalhes de algum. | Property ID favorito → SI-A |
| **5. Sem resultados — fallback progressivo** | Se nenhum imóvel corresponde aos critérios exactos, tenta alternativas antes de desistir, por esta ordem: **(1)** Mesma zona e orçamento, tipologia diferente — *"Não tenho moradias nessa zona até €250k, mas tenho apartamentos T3/T4 com características semelhantes. Quer que lhe mostre?"* **(2)** Mesma tipologia e orçamento, zona alargada — *"Não tenho nada na zona de praia, mas tenho moradias a 10-15 min com perfil semelhante e melhor relação qualidade-preço."* **(3)** Ambas as variáveis flexíveis — apresenta a opção mais próxima disponível. Só regista alerta de perfil se o cliente recusar todas as alternativas. | Critérios flexibilizados, alternativas apresentadas, alerta criado apenas se necessário |
| **6. Cross-sell angariação** | No fecho pergunta: *"Só para completar o seu perfil — tem algum imóvel para vender ou arrendar?"* Se sim: identifica tipo e localização; pergunta se já está à venda; se sim, se está com agências ou só a nível particular. | Tipo/morada, estado |
| **7. Registo duplo** | Se houver imóvel para vender: cria **DUAS oportunidades** — (1) compra com perfil e critérios do comprador; (2) angariação com dados do imóvel do cliente e estado actual. Transfere contexto de angariação para A4. | Oportunidade compra + angariação criadas |
| **8. Conversão** | Propõe visita ao imóvel favorito → activa fluxo **SV**. | Sub-intenção SV |

#### SV — Visitar Imóvel

> ⚠️ **Princípio-chave:** nunca marcar visita sem qualificação prévia. Antes de confirmar qualquer data, o assistente verifica se o orçamento declarado é compatível com o imóvel pretendido. **Regra: o orçamento deve ser ≥ 80% do preço de venda.** Abaixo deste limiar, a visita não é marcada e o cliente é reencaminhado para alternativas.

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Identificação do imóvel** | Confirma o imóvel que o cliente quer visitar (por referência, morada ou descrição). Faz lookup silencioso para obter preço. | Property ID, preço |
| **2. Qualificação obrigatória** | Pergunta: *"Para confirmar a visita, posso saber qual o orçamento aproximado que tem disponível para esta aquisição?"* | Orçamento declarado |
| **3a. Orçamento compatível (≥ 80% do preço)** | Prossegue com marcação. Verifica disponibilidade do consultor e propõe 2-3 slots horários. | Datas disponíveis |
| **3b. Orçamento abaixo do limiar (< 80% do preço)** | **Não marca a visita.** Resposta: *"Este imóvel tem um valor de [X€], o que está acima do seu orçamento. Para garantir que a visita seja produtiva, prefiro procurar imóveis com características semelhantes que se enquadrem melhor. Posso ajudá-lo dessa forma?"* → Activa **SI-B** com perfil já recolhido. | Perfil reencaminhado para SI-B |
| **3c. Orçamento não declarado** | Insiste com contexto: *"Para preparar melhor a visita e garantir que corresponde às suas expectativas, ajuda-nos saber o intervalo de investimento que tem em mente. Não é compromisso nenhum."* Se o cliente persistir em não declarar, **escala para consultor humano**. | Nota de escalada |
| **4. Dados de contacto** | Pede nome completo e telefone para confirmação da visita. | Nome, telefone |
| **5. Confirmação** | Envia resumo: data, hora, morada do imóvel, nome do consultor responsável. | Booking ID criado (`ai_visit_bookings`) |
| **6. Lembrete** | **24h antes**: envia lembrete automático com pedido de confirmação de presença. | Estado da visita actualizado |
| **7. Follow-up** | **48h após a visita**: pergunta feedback e interesse em avançar (proposta, simulação de crédito ou outras opções). | Feedback, próximo passo |

> 💡 **Exemplo prático — Regra dos 20%:** imóvel a €300k. Cliente declara orçamento de €240k (= 80% do preço — limiar exacto). O assistente pode prosseguir, mas acrescenta: *"Este imóvel está ligeiramente acima do orçamento indicado. O consultor poderá esclarecer as condições em detalhe durante a visita."* Se o cliente declarar €200k (< 67% do preço), **não marca a visita** e activa SI-B com os critérios já conhecidos.

#### SC — Simular Crédito

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Dados do imóvel** | Confirma o valor do imóvel em análise. | Preço do imóvel |
| **2. Dados financeiros** | Pergunta entrada disponível (%) e prazo desejado (anos). | Entrada, prazo |
| **3. Simulação indicativa** | Calcula prestação estimada com taxa euribor + spread médio de mercado. Apresenta tabela simples. | Resultados da simulação |
| **4. Nota legal** | Informa que é **simulação indicativa** e recomenda consulta com banco/broker. | — |
| **5. Oferta de apoio** | Pergunta se quer ser contactado por parceiro de crédito da agência. | Consentimento de contacto |
| **6. Registo** | Cria lead com dados de simulação e preferência de crédito. | Lead ID + flag crédito |

#### FP — Fazer Proposta

> ⚠️ **Princípio-chave:** o assistente **nunca aceita nem recusa uma proposta** — analisa o valor, qualifica a motivação do cliente e regista todos os dados antes de escalar para o consultor. Margem de negociação habitual da agência: **~3% abaixo do preço de venda**. Propostas com desvio **> 15%** requerem abordagem especial.

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Identificação** | Confirma o imóvel sobre o qual o cliente pretende fazer proposta (referência ou descrição). Lookup silencioso para obter preço de venda actual. | Property ID, preço de venda |
| **2. Valor da proposta** | Pergunta: *"Qual o valor que pretende propor?"* | Valor proposto |
| **3a. Proposta pelo preço pedido (desvio 0%)** | Aceita de imediato: *"Excelente! A proposta pelo valor do imóvel será registada com prioridade. Vamos recolher os dados para formalizar."* Prossegue directamente para fase 4. | Flag: proposta ao preço |
| **3b. Proposta abaixo mas dentro da margem (desvio 1–15%)** | Prossegue para recolha de dados completos (fase 4) **sem qualquer comentário sobre o valor**. Coloca exactamente as mesmas perguntas que no ramo A: financiamento, prazo CPCV, valor final e data de escritura. | — |
| **3c. Proposta com desvio > 15% abaixo do preço** | **Abordagem educativa (não rejeita):** *"O imóvel que escolheu está avaliado ao preço de mercado e foi posicionado criteriosamente. Pode partilhar o que o leva a considerar que o valor está acima do esperado? Isso ajuda-nos a preparar melhor a conversa com o consultor."* Regista a justificação. Informa que a proposta será analisada pelo consultor. | Justificação do cliente, flag desvio > 15% |
| **4. Dados de financiamento** | *"A aquisição será a pronto pagamento ou com recurso a crédito habitação?"* Se crédito: *"Já tem aprovação bancária ou necessita de apoio no processo de crédito? Temos parceiros especializados que podem ajudar."* | Forma de pagamento, necessidade de crédito |
| **5. Condição de compra** | *"A compra pode ser realizada de imediato, ou existe alguma condição que dependa de um factor externo — por exemplo, a venda de outro imóvel?"* Se condicionada: identifica se esse imóvel já está à venda, com quem, e qual o estado do processo. Regista o tipo: **firme** ou **condicionada**. | Tipo de proposta, estado do imóvel a vender |
| **6. Dados da proposta formal** | Recolhe: nome completo, telefone, email, prazo para contrato promessa (CPCV), valor final proposto, data pretendida para escritura. | Nome, telefone, email, prazo CPCV, valor final, data escritura |
| **7. Confirmação e registo** | Envia resumo completo: imóvel, valor proposto, tipo de proposta, condições de financiamento, datas. Confirma: *"A sua proposta foi registada. O consultor responsável entrará em contacto consigo em breve para dar seguimento."* | Proposta completa registada na BD |
| **8. Escalada ao consultor** | Notifica o consultor com contexto completo: imóvel, valor proposto, desvio face ao preço, tipo de proposta (firme/condicionada + estado do imóvel a vender), justificação (se desvio > 15%), financiamento, contacto, prazos. | Notificação enviada, timestamp |
| **9. Follow-up interno** | Se o consultor não confirmar recepção em **2h úteis**, reforça a notificação com flag de urgência. | Status escalada |

> 💡 **Exemplo de abordagem para desvio > 15%:** imóvel a €300k, cliente propõe €240k (−20%). O assistente **não diz "não"** — pergunta a motivação, regista, informa que o consultor vai analisar e contactar. O consultor decide se avança ou contrapõe. **O assistente nunca negoceia nem dá indicação de margem disponível.**

### 3.3 Perguntas Típicas e Respostas

> ⚠️ **Princípio de qualificação paralela:** o assistente **NUNCA responde apenas à pergunta**. Enquanto procura a informação pedida, aproveita para qualificar o cliente em simultâneo — o que procura, orçamento, e **se tem algum imóvel para vender**. Esta última pergunta é **SEMPRE** feita, sem excepção, em qualquer conversa com um cliente comprador.

| Pergunta do Cliente | Abordagem do Assistente A1 |
|--------------------|---------------------------|
| **"Quanto é o T2 que vi no vosso site?" (SI)** | *"Já procuro essa informação para si. Enquanto isso, posso perguntar — está à procura de T2 nesta zona especificamente, ou está em aberto? E qual o orçamento que tem em mente?"* Apresenta a ficha com preço após qualificação contextual. No final: pergunta se tem imóvel para vender. |
| **"Têm casas em [zona]?" (SI)** | *"Temos imóveis em [zona], sim. Para lhe mostrar as opções mais adequadas — que tipologia procura e qual o orçamento disponível?"* Apresenta até 3 opções. No final: pergunta se tem imóvel para vender. |
| **"Ainda está disponível?" (SI)** | Verifica estado em tempo real na BD. Se disponível: *"Está disponível! Quer que lhe envie a ficha completa? E posso perguntar — é para compra ou arrendamento, e qual o orçamento aproximado?"* |
| **"Quanto custa o condomínio?" (SI)** | Verifica ficha do imóvel na BD. Se o dado existir: responde directamente. Se não: informa que encaminha para o consultor responsável — e aproveita para qualificar: *"Já visitou este imóvel? Tem interesse em avançar ou ainda está numa fase de análise? Pretende fazer uma proposta?"* Regista as respostas e passa o contexto completo ao consultor. |
| **"Posso ver o imóvel este fim-de-semana?" (SV)** | Antes de confirmar: qualifica orçamento (**regra dos 80%**). Se compatível: verifica agenda e propõe 2-3 horários. Recolhe nome e telefone. No final: pergunta se tem imóvel para vender. |
| **"Quanto fico a pagar por mês?" (SC)** | Activa fluxo SC: pergunta entrada e prazo, calcula prestação estimada e oferece parceiro de crédito. No final: pergunta se tem imóvel para vender. |
| **"Quero fazer uma oferta" (FP)** | Activa fluxo FP completo: qualifica valor da proposta, recolhe financiamento, prazos CPCV e escritura. No final: pergunta se tem imóvel para vender. |
| **"O preço é negociável?" (FP)** | **Não responde directamente** se é ou não negociável. Qualifica: *"Posso perguntar qual o valor que teria em mente?"* Aplica então as regras do fluxo FP: dentro dos 15% → activa FP e recolhe todos os dados; desvio > 15% → abordagem educativa, pergunta a motivação, e escala para consultor com flag. **Nunca confirma nem nega margem de negociação.** |
| **"Quero algo diferente do que têm" (SI)** | Regista perfil como **alerta activo** e promete contactar quando surgir imóvel adequado. Pergunta se tem imóvel para vender — pode ser uma troca. |

> 💡 **Frase-padrão de qualificação paralela:** *"Enquanto procuro essa informação, posso fazer-lhe uma pergunta rápida?"* — abre espaço para qualificar sem interromper o fluxo. A pergunta sobre imóvel para venda vem sempre no fecho natural: *"Só para completar o seu perfil — tem algum imóvel para vender ou arrendar?"*

### 3.4 Regras de Escalada

- **FP (Fazer Proposta)** → escalada imediata e obrigatória para consultor, sem excepções
- **Negociação de preço** em qualquer ponto → escalada imediata com contexto completo
- **Mais de 3 perguntas técnicas** (escritura, certidões, usucapião) → escala para consultor sénior
- **Tom de frustração detectado** → escala com prioridade alta
- **Fora do horário de trabalho** → o assistente funciona normalmente **24/7**: responde a questões, qualifica clientes, apresenta fichas e regista leads. Só quando é necessária intervenção humana (escalada, visita, proposta, questão sem resposta) informa o cliente que será contactado pelo consultor no próximo dia útil.

### 3.5 Fonte de Conhecimento

- Tabela `properties` no Supabase (dados em tempo real dos imóveis activos)
- Tabela `agency_info` (políticas de comissão, áreas de actuação)
- FAQ sobre processo de compra/arrendamento em Portugal (ficheiro base de conhecimento estático)
- Tabela `consultants` (para atribuição de responsável e disponibilidade)

---

## 4. A2 — Atendimento Geral

> 📞 **A2 — Atendimento Geral:** Recepciona e encaminha todas as questões gerais da agência.

### 4.1 Objectivo

Funcionar como **recepcionista virtual** da agência. Responde a questões institucionais, reencaminha para o assistente correcto e garante que nenhum contacto fica sem resposta, independentemente do motivo.

### 4.2 Fluxo de Conversação

| Situação | Acção do A2 |
|----------|------------|
| **Questão institucional (horários, morada, serviços)** | Responde directamente com informação da tabela `agency_info` |
| **Intenção de compra/arrendamento detectada** | Transfere thread para **A1** com contexto já recolhido |
| **Intenção de venda/angariação detectada** | Transfere thread para **A4** com contexto já recolhido |
| **Intenção de candidatura/recrutamento** | Transfere thread para **A3** com contexto já recolhido |
| **Reclamação ou assunto sensível** | Escala imediatamente para gestor / consultor responsável |
| **Questão jurídica ou fiscal complexa** | Informa que encaminha para especialista, recolhe dados de contacto |
| **Contacto de imprensa ou parceria** | Recolhe dados e encaminha para direcção |
| **Sem intenção clara após 2 trocas** | Apresenta menu de opções: Comprar / Vender / Arrendar / Trabalhar connosco / Outro |

### 4.3 Perguntas Típicas

| Pergunta | Resposta / Acção |
|----------|-----------------|
| **"Qual é o vosso horário?"** | Horário completo da agência da tabela `agency_info` |
| **"Onde ficam localizados?"** | Morada(s) e link Google Maps |
| **"Com quem posso falar sobre X?"** | Identifica o departamento certo e fornece contacto directo ou transfere |
| **"Quais os serviços que oferecem?"** | Lista completa: mediação compra/venda, arrendamento, avaliação, gestão de imóveis |
| **"Têm parceiros de crédito habitação?"** | Lista de parceiros bancários e/ou broker de crédito |
| **"Posso falar com uma pessoa?"** | Confirma dados e agenda callback com consultor disponível |
| **"Tenho uma reclamação"** | Escala imediatamente, regista com prioridade alta, promete resposta em 24h |

### 4.4 Regras de Escalada

- Qualquer menção a **advogado, tribunal ou processo legal** → escala imediata + registo de urgência
- **Cliente insatisfeito** ou linguagem negativa repetida → escala com marcação de prioridade
- **Questão não coberta** pelo conhecimento base → admite limitação e promete resposta humana
- **Jornalistas, parcerias institucionais** → encaminha para direcção

---

## 5. A3 — Assistente de Recrutamento

> 👤 **A3 — Assistente de Recrutamento:** Responde a candidatos e qualifica leads de consultores imobiliários.

### 5.1 Objectivo

Qualificar e nutrir candidatos que pretendem tornar-se consultores imobiliários na agência. O assistente apresenta o modelo de negócio, responde a dúvidas sobre a carreira e agenda entrevistas com o responsável de recrutamento.

### 5.2 Fluxo de Conversação

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Acolhimento** | Apresenta-se, agradece o interesse, confirma que é para recrutamento | Intenção confirmada |
| **2. Contexto** | Pergunta contexto profissional actual (área, anos de experiência) | Profissão actual, experiência em imobiliário |
| **3. Motivação** | Pergunta o que o atraiu para o sector imobiliário | Motivação, expectativas |
| **4. Apresentação** | Explica o modelo da agência: comissões, formação, suporte, área de trabalho | — |
| **5. Qualificação** | Pergunta disponibilidade (full-time/part-time), zona preferencial de actuação | Disponibilidade, zona |
| **6. Próximo passo** | Propõe entrevista (presencial ou vídeo) com responsável de recrutamento | Data/hora preferida |
| **7. Confirmação** | Envia confirmação com local/link + o que esperar na entrevista | Recruitment lead ID criado |

### 5.3 Perguntas Típicas

| Pergunta do Candidato | Abordagem do A3 |
|----------------------|----------------|
| **"Preciso de experiência para ser consultor?"** | Não é necessária experiência prévia. Explica o programa de formação inicial e o acompanhamento de um mentor. |
| **"Qual é o salário base?"** | Explica o modelo de comissões: rendimento variável, sem tecto. Exemplifica com cenários realistas de consultores activos. |
| **"É possível trabalhar a part-time?"** | Confirma que sim, explica flexibilidade de horário e que os resultados dependem do tempo dedicado. |
| **"Que formação vou receber?"** | Descreve o programa de integração: formação de produto, legal, técnicas de venda, CRM. |
| **"Tenho de ter carro?"** | Confirma necessidade de viatura própria para visitas a imóveis. |
| **"Quanto tempo leva a ter os primeiros rendimentos?"** | Apresenta timelines realistas (média **60-90 dias** para primeira transacção) e o que a agência faz para acelerar. |
| **"Como é a progressão na carreira?"** | Explica níveis (consultor júnior → sénior → team leader) e os critérios de progressão. |
| **"Posso trazer a minha carteira de clientes?"** | Confirma que sim, é uma vantagem. O CRM da agência suporta migração de contactos. |

### 5.4 Conteúdo de Conhecimento Base

- Modelo de remuneração e estrutura de comissões (documento interno)
- Programa de formação inicial e contínua
- Benefícios: CRM, marketing, suporte jurídico, leads da agência
- Zonas de actuação disponíveis e consultores activos por zona
- Testemunhos / casos de sucesso de consultores (opcional)
- FAQs sobre licença AMI e requisitos legais do consultor imobiliário em Portugal

---

## 6. A4 — Assistente Angariador

> 🔑 **A4 — Assistente Angariador:** Qualifica proprietários com interesse em angariar o seu imóvel.

### 6.1 Objectivo

Qualificar proprietários que pretendam colocar o seu imóvel à venda ou arrendamento através da agência. O assistente recolhe dados do imóvel, explica o processo e agenda uma **visita de avaliação** com um consultor especialista em angariações.

### 6.2 Fluxo de Conversação

| Fase | O Assistente Faz | Dados Recolhidos |
|------|-----------------|-----------------|
| **1. Confirmação de intenção** | Clarifica se quer vender, arrendar ou ambas as opções | Intenção (venda/arrendamento) |
| **2. Dados do imóvel** | Pergunta tipo, localização, área aproximada e estado de conservação | Tipologia, morada, área, estado |
| **3. Expectativas** | Pergunta valor expectável e prazo desejado para transacção | Valor esperado, urgência |
| **4. Situação legal** | Pergunta se o imóvel tem hipoteca activa ou outros ónus | Situação hipotecária |
| **5. Proposta de valor** | Explica serviços: avaliação gratuita, marketing digital, rede de compradores, suporte jurídico | — |
| **6. Diferenciação** | Destaca dados concretos: tempo médio de venda, preço médio obtido vs. mercado | — |
| **7. Agendamento** | Propõe visita de avaliação ao imóvel (**sem compromisso**) | Data, hora, morada exacta |
| **8. Confirmação** | Confirma agendamento e nome do consultor que vai à visita | Angariação lead ID criado |

### 6.3 Perguntas Típicas

| Pergunta do Proprietário | Abordagem do A4 |
|-------------------------|----------------|
| **"Quanto vale a minha casa?"** | Explica que a avaliação rigorosa é feita presencialmente (gratuita e sem compromisso) e propõe agendamento. Pode dar estimativa de intervalo com base na zona e tipologia. |
| **"Qual é a vossa comissão?"** | Informa a comissão standard e destaca o que está incluído (marketing, jurídico, acompanhamento). Reforça que **só se paga quando o negócio fecha**. |
| **"Porque devo trabalhar com uma agência?"** | Apresenta dados: velocidade média de venda, alcance da rede, suporte no processo legal e negociação, sem custos antecipados. |
| **"Posso ter mais que uma agência ao mesmo tempo?"** | Explica as diferenças entre exclusividade e não-exclusividade e os benefícios do contrato em exclusivo para o proprietário. |
| **"Como divulgam o imóvel?"** | Descreve canais: portais imobiliários (Idealista, Imovirtual, Casa Sapo), redes sociais, base de dados de compradores activos, newsletter. |
| **"Quanto tempo demora a vender?"** | Partilha o tempo médio de venda da agência na zona e factores que influenciam (preço, estado, documentação). |
| **"O imóvel tem uma hipoteca, posso vender?"** | Confirma que sim, é comum, e que o consultor orientará no processo. **Não entra em detalhes jurídicos.** |
| **"Não quero ninguém a entrar em casa"** | Explica que a visita de avaliação é discreta (apenas o consultor) e que visitas posteriores são agendadas e acompanhadas. |

### 6.4 Conteúdo de Conhecimento Base

- Serviços de angariação e o que está incluído no contrato
- Estrutura de comissões e condições de pagamento
- Dados de desempenho: tempo médio de venda por zona e tipologia (da tabela `imoveis`)
- Processo de documentação necessária para venda/arrendamento em Portugal
- Comparativo exclusividade vs. não-exclusividade
- Programa de marketing: portais, redes sociais, base de dados de compradores

---

## 7. Especificações por Canal

### 7.1 WhatsApp Business

| Aspecto | Especificação |
|---------|--------------|
| **API** | WhatsApp Business API (Meta) via provedor: Twilio, 360dialog ou WATI |
| **Templates** | Necessários para mensagens de iniciativa (confirmações, follow-ups). Templates aprovados pela Meta. |
| **Sessão de 24h** | Mensagens livres apenas nas 24h após mensagem do utilizador. Follow-ups fora deste período requerem template. |
| **Media** | Envio de fichas em PDF, imagens de imóveis, links de visita virtual |
| **Botões** | Até 3 botões de resposta rápida (ex: "Quero visitar", "Saber mais", "Outro imóvel") |
| **Limite de texto** | 4096 caracteres — dividir mensagens longas em blocos lógicos de máx. 300 palavras |
| **Número dedicado** | Recomenda-se um número por função (Vendas, Geral, Recrutamento, Angariações) para roteamento automático |

### 7.2 Email

| Aspecto | Especificação |
|---------|--------------|
| **Provedor** | SendGrid, Mailgun ou SMTP da agência |
| **Formato** | HTML responsivo com logo da agência no cabeçalho e assinatura no rodapé |
| **Assunto** | Gerado dinamicamente com base na intenção |
| **Tempo de resposta** | Alvo: **< 5 minutos** (automação 24/7) |
| **Attachments** | Fichas de imóveis em PDF, documentos informativos |
| **Thread** | Responder sempre no mesmo thread de email para manter contexto |
| **Assinatura** | Nome do assistente + "Agência [Nome] \| assistido por IA" + contacto humano alternativo |

### 7.3 SMS

| Aspecto | Especificação |
|---------|--------------|
| **Provedor** | Twilio SMS ou Vonage |
| **Limite** | 160 caracteres por SMS (concatenados se necessário, mas preferir concisão) |
| **Uso ideal** | Confirmações de visita, lembretes 24h antes, follow-ups simples |
| **Não usar para** | Conversas longas — redirigir para WhatsApp ou Email |
| **Opt-out** | Resposta **STOP** deve desactivar automaticamente envios futuros (obrigação legal) |

### 7.4 Voz (Voice)

| Aspecto | Especificação |
|---------|--------------|
| **Tecnologia** | Twilio Voice + TTS (Text-to-Speech) + STT (Speech-to-Text) |
| **TTS Engine** | Google Cloud TTS (voz pt-PT) ou ElevenLabs para voz mais natural |
| **STT Engine** | OpenAI Whisper ou Google Cloud STT (suporte a sotaques PT) |
| **IVR inicial** | *"Bem-vindo à [Agência]. Diga o motivo do contacto ou prima 1 para compra, 2 para vender, 3 para trabalhar connosco."* |
| **Escalada para humano** | Opção sempre disponível: *"Prima 0 ou diga CONSULTOR para falar com um agente"* |
| **Fora de horas** | Mensagem personalizada + opção de deixar recado (transcrito via STT e guardado no Supabase) |
| **Resposta máxima** | Frases curtas, **máx. 3 frases por turno**. Sem listas ou tabelas. |

---

## 8. Privacidade e Conformidade (RGPD)

### 8.1 Obrigações

- **Identificação obrigatória** — o assistente deve identificar-se como IA no início de cada conversa
- **Consentimento** — antes de recolher dados pessoais, deve apresentar uma declaração de privacidade simplificada
- **Direito ao esquecimento** — processo de anonimização de dados implementado na BD (soft delete com `deleted_at`)
- **Não partilha de dados** — os dados recolhidos não são partilhados com terceiros sem consentimento
- **Retenção de dados** — conversas activas **12 meses**, leads não convertidos **24 meses**

### 8.2 Declaração de Início de Conversa

> *"Olá! Sou um assistente virtual da [Agência Imobiliária]. Vou recolher alguns dados para poder ajudá-lo melhor. Os seus dados são tratados de acordo com o RGPD e a nossa política de privacidade. Pode pedir para falar com um humano a qualquer momento."*

---

## 9. Roadmap de Implementação

| Fase | O que entregar | Prazo estimado |
|------|---------------|---------------|
| **Fase 1 — Fundação** | Configurar Supabase (tabelas, RLS). Criar conta WhatsApp Business API. Integrar Claude API. Implementar **A2 (Geral)** no WhatsApp. | 2-3 semanas |
| **Fase 2 — Assistente Vendedor** | Implementar **A1** com os fluxos SI-A, SI-B, SV, SC e FP. Testar qualificação contextual e roteamento dinâmico. | 3-4 semanas |
| **Fase 3 — Angariador e Recrutamento** | Implementar **A4** e **A3**. Criar knowledge base estático para cada um. | 2-3 semanas |
| **Fase 4 — Email e SMS** | Ligar canais Email (SendGrid) e SMS (Twilio). Adaptar respostas ao formato de cada canal. | 1-2 semanas |
| **Fase 5 — Voz** | Implementar canal de voz com TTS/STT. Configurar IVR. Testar em ambiente real. | 3-4 semanas |
| **Fase 6 — Optimização** | Análise de logs, ajuste de prompts, métricas de qualificação, dashboard de leads. | Contínuo |

### 9.1 Métricas de Sucesso

| Métrica | Alvo |
|---------|------|
| **Taxa de qualificação** — % de contactos que passam para lead qualificado | > 40% |
| **Taxa de marcação de visita** — % de leads A1 que agendam visita | > 25% |
| **Tempo médio de resposta** — em qualquer canal | < 2 minutos |
| **Taxa de escalada desnecessária** — % de escaladas que o assistente podia ter resolvido | < 15% |
| **Leads de angariação qualificados** | Nº de agendamentos de avaliação por mês |

---

## Anexo — Regras Críticas (Checklist para Implementação)

Regras transversais que **devem ser codificadas** nos system prompts e na lógica de automação:

1. **Deduplicação obrigatória** — pesquisar sempre (telefone → email → nome) antes de criar qualquer registo.
2. **Regra dos 80%** — não marcar visita se o orçamento declarado for < 80% do preço do imóvel.
3. **Não revelar preço antes de qualificar** (SI-A) — 2 perguntas contextuais primeiro.
4. **Cross-sell angariação sempre** — pergunta "tem algum imóvel para vender ou arrendar?" no fecho de toda a conversa A1.
5. **Registo duplo** — comprador com imóvel para vender gera 2 oportunidades no mesmo contacto.
6. **FP escala sempre** — o assistente nunca aceita, recusa nem negoceia propostas.
7. **Desvio > 15%** — abordagem educativa, recolher motivação, escalar com flag.
8. **Fallback progressivo em SI-B** — 3 níveis de flexibilização antes de registar alerta.
9. **Identificação como IA** no início de cada conversa (RGPD).
10. **Soft delete** — nunca apagar conversas; logs de mensagens são write-once.
11. **Service role key** apenas no servidor; RLS activo em todas as tabelas novas.
12. **24/7** — o assistente responde sempre; só a intervenção humana fica para o dia útil seguinte.

---

*Documento original preparado com assistência de IA — Claude (Anthropic) | Junho 2026*
