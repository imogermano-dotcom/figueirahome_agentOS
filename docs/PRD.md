# PRD — Figueirahome Agent Call

> Product Requirements Document. Descreve o **o quê** e o **porquê** do produto. Para detalhe técnico, ver `database-schema.md`, `api-spec.md` e `architecture.md`.

---

## 1. Visão geral

O Figueirahome Agent Call é uma plataforma de IA para uma agência imobiliária em Portugal. Automatiza o atendimento telefónico e dá ao broker um assistente inteligente com acesso a todos os dados do negócio.

### Objectivos
- Atender chamadas telefónicas automaticamente, 24/7, em Português de Portugal.
- Recolher e estruturar dados de potenciais clientes sem intervenção humana.
- Dar ao broker respostas instantâneas sobre clientes, imóveis e leads.
- Centralizar a gestão num único painel web.

### Utilizadores
- **Developer** (você) — configura, mantém e desenvolve.
- **Dono da agência** — usa o painel, configura agentes, consulta dados.

---

## 2. Agente 1 — Atendimento de Voz

### Propósito
Atender chamadas recebidas, conversar naturalmente com quem liga, e recolher informação útil para o negócio.

### Requisitos funcionais
- Atender automaticamente chamadas recebidas no número Telnyx.
- Conversar em Português de Portugal com voz natural.
- Compreender o que o cliente diz (transcrição em tempo real).
- Recolher: nome, contacto, tipo de interesse (compra/arrendamento), orçamento, zona preferida.
- Registar imóveis mencionados pelo cliente (ex: proprietário que quer vender).
- Criar automaticamente um registo de cliente e um lead na base de dados.
- Gravar e transcrever a chamada completa.
- Gerar um resumo da chamada com IA.
- Funcionar com persona e instruções configuráveis no painel (sem mexer no código).

### Requisitos não funcionais
- Latência baixa — a conversa tem de fluir naturalmente. Processar áudio em chunks.
- Fiabilidade — uma chamada perdida tem custo real. O servidor não pode falhar.

### Fora de âmbito (por agora)
- Fazer chamadas de saída (apenas recebe).
- Transferir para humano (futuro).

---

## 3. Agente 2 — Assistente do Broker

### Propósito
Dar ao broker um assistente conversacional com acesso a toda a base de dados, acessível por vários canais.

### Requisitos funcionais
- Interface de chat web integrada no painel.
- Responder a perguntas sobre clientes, imóveis e leads consultando o Supabase em tempo real.
  - Ex: "Que imóveis tenho em Coimbra abaixo de 200 mil?"
  - Ex: "Quais os clientes que ligaram esta semana à procura de moradias?"
- Suportar múltiplos canais: chat web (nativo), WhatsApp, Telegram, email.
- Guardar histórico de conversas por canal.
- Responder sempre em Português de Portugal.

### Canais — prioridade
1. Chat web (essencial para o arranque).
2. WhatsApp (via Telnyx).
3. Telegram.
4. Email.

### Fora de âmbito (por agora)
- Acções de escrita iniciadas pelo agente (ex: criar/apagar imóveis). Por agora, só leitura e resposta. A escrita é feita pelo painel ou pelo Agente 1.

---

## 4. Painel Web de Gestão

### Propósito
Interface única para gerir todo o sistema.

### Secções
- **Dashboard** — chamadas do dia/semana, leads novos, conversas activas, imóveis disponíveis.
- **Agente 1 — Configuração** — editar persona, tom e instruções; activar/pausar.
- **Agente 1 — Chamadas** — histórico com transcrição, resumo IA, gravação e dados recolhidos.
- **Agente 2 — Chat** — chat ao vivo com o assistente + histórico por canal.
- **Agente 2 — Canais** — gerir ligações a WhatsApp, Telegram, email.
- **Clientes** — tabela com filtros, pesquisa, edição inline, exportar CSV.
- **Imóveis** — tabela com filtros; importar CSV; adicionar manual; ver origem.
- **Leads** — pipeline com estado, notas, filtros.
- **Configuração Geral** — credenciais (Telnyx, Supabase), utilizadores, número activo.

### Autenticação
- Login via Supabase Auth.
- Dois utilizadores: developer e dono da agência.

---

## 5. Imóveis — múltiplas fontes

Os imóveis podem entrar no sistema por várias origens. O campo `fonte` regista de onde vieram:
- `idealista` / `imovirtual` — portais (integração futura).
- `agente_voz` — recolhidos pelo Agente 1 numa chamada.
- `manual` — adicionados no painel.
- `csv` — importados em lote.

---

## 6. Fases de implementação

### Fase 1 — Fundação ← **ACTUAL**
Estrutura base, Supabase com todas as tabelas, servidor FastAPI base, frontend base, autenticação.

### Fase 2 — Agente de Voz
Webhook Telnyx, streaming WebSocket, Whisper, Claude API, TTS, gravação de dados.

### Fase 3 — Agente Broker
Chat web com Claude API e acesso à base de dados; depois WhatsApp, Telegram, email.

### Fase 4 — Painel Admin
Dashboard, gestão de clientes/imóveis/leads, config de agentes, histórico de chamadas, import CSV.

### Fase 5 — Futuro
Idioma Inglês, integração com portais, relatórios avançados, app mobile.

---

## 7. Critérios de sucesso

- O Agente 1 atende uma chamada e cria correctamente um cliente + lead no Supabase.
- O Agente 2 responde correctamente a uma pergunta sobre dados reais da base de dados.
- O dono da agência consegue configurar a persona do Agente 1 sem ajuda técnica.
- O sistema corre de forma fiável em produção.
