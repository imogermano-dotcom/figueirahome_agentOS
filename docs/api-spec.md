# API Spec — Figueirahome Agent Call (FastAPI)

> Especificação dos endpoints do backend. Para a Fase 1, só os endpoints de **fundação** são implementados (health check, config, CRUD básico). Os endpoints dos agentes (voz, broker) ficam definidos aqui mas só são implementados nas Fases 2 e 3.

---

## Base

- Framework: FastAPI (async).
- Base URL local: `http://localhost:8000`
- Prefixo da API do painel: `/api`
- Documentação automática: `/docs` (Swagger).

---

## FASE 1 — Endpoints de fundação

### Health & sistema
```
GET  /health
     → { "status": "ok", "version": "..." }
     Verifica que o servidor está vivo. Usado pela Telnyx e pelo deploy.
```

### Config dos agentes
```
GET  /api/config/{agente}
     agente = 'voz' | 'broker'
     → devolve persona, instrucoes, idioma, ativo

PUT  /api/config/{agente}
     body: { persona, instrucoes, idioma, ativo }
     → actualiza a configuração do agente
```

### Clientes (CRUD)
```
GET    /api/clientes               → lista (com query params: ?search=&zona=&tipo=)
GET    /api/clientes/{id}          → detalhe
POST   /api/clientes               → criar
PUT    /api/clientes/{id}          → actualizar
DELETE /api/clientes/{id}          → apagar
```

### Imóveis (CRUD + import)
```
GET    /api/imoveis                → lista (?estado=&fonte=&tipo=&localizacao=)
GET    /api/imoveis/{id}           → detalhe
POST   /api/imoveis                → criar
PUT    /api/imoveis/{id}           → actualizar
DELETE /api/imoveis/{id}           → apagar
POST   /api/imoveis/import         → importar CSV (multipart/form-data)
```

### Leads (CRUD)
```
GET    /api/leads                  → lista (?estado=&cliente_id=&imovel_id=)
GET    /api/leads/{id}             → detalhe
POST   /api/leads                  → criar
PUT    /api/leads/{id}             → actualizar
DELETE /api/leads/{id}             → apagar
```

### Leads da Meta — semeadura (implementado 2026-08-12 — `api/leads_meta.py`)
```
POST /api/leads/{lead_id}/conversa-semeada    body: {"template": "<texto enviado>"}
     → cria/actualiza o cliente, semeia a thread do A1 e marca a lead `contactada`
     → 200 {lead_id, cliente_id, conversa_id, ja_existia}
     → 404 lead inexistente · 422 tipo != compra/arrendamento, ou lead sem telefone
```
Chamado pelo **n8n** logo após enviar o template de WhatsApp. Autenticação:
`X-Automacao-Secret` **ou** JWT — `deps.require_automacao_access`. Segredo
distinto do `X-Sync-Secret` de propósito: quem ingere leads não tem de poder
disparar syncs do eGO.

Existe porque a resposta a um template é quase sempre "Sim" ou "Olá", que
`router._A1_RE` não reconhece — sem a thread semeada com `agente='a1_vendedor'`
a lead cai no A2. O texto do template entra no histórico como `assistant`, para
o A1 não repetir o que já foi dito. Idempotente: repetir a chamada com a lead já
semeada devolve `ja_existia: true` sem tocar na conversa.

O **Make escreve em `leads` directamente pelo PostgREST** — não há endpoint de
ingestão.

### Dashboard
```
GET  /api/dashboard
     → métricas agregadas: chamadas_hoje, leads_novos,
       conversas_activas, imoveis_disponiveis
```

> **Nota:** todos os endpoints `/api/*` exigem autenticação (token Supabase no header `Authorization: Bearer ...`). Implementar o middleware de auth na Fase 1.

---

## FASE 2 — Endpoints do Agente de Voz (não implementar ainda)

```
POST /webhook/telnyx
     Recebe eventos da Telnyx (call.initiated, call.answered,
     call.hangup, etc.). Responde com comandos de call control.
     Verificar assinatura do webhook.

WS   /ws/audio/{call_control_id}
     WebSocket para streaming de áudio bidireccional com a Telnyx.
     Recebe áudio (base64 RTP) → Whisper → Claude → TTS → devolve áudio.
```

Fluxo interno do Agente de Voz:
```
call.initiated → atender (Telnyx API)
              → iniciar streaming WebSocket
              → loop: áudio recebido → STT → Claude (com persona da config)
                     → resposta → TTS → áudio enviado
call.hangup   → guardar chamada (transcrição, resumo IA, dados recolhidos)
              → criar/actualizar cliente + lead no Supabase
```

---

## FASE 3 — Endpoints do Agente Broker (não implementar ainda)

```
POST /api/broker/chat
     body: { mensagem, conversa_id? }
     → resposta do agente. Internamente: Claude API com acesso à
       base de dados (consulta clientes/imoveis/leads conforme a pergunta).
     → guarda em 'conversas'.

POST /webhook/whatsapp     (futuro)
POST /webhook/telegram     (futuro)
POST /webhook/email        (futuro)
```

O agente broker usa **tool calling** da Claude API para consultar a base de dados:
- `consultar_clientes(filtros)`
- `consultar_imoveis(filtros)`
- `consultar_leads(filtros)`

---

## Modelos de dados (Pydantic)

Definir em `backend/app/models/`. Espelham as tabelas do `database-schema.md`. Exemplos:

```python
# models/cliente.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

class ClienteBase(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    tipo_interesse: Optional[str] = None
    orcamento: Optional[float] = None
    zona_preferida: Optional[str] = None
    notas: Optional[str] = None
    origem: Optional[str] = None

class ClienteCreate(ClienteBase):
    pass

class Cliente(ClienteBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime
```

---

## Notas para o Claude Code

- Na Fase 1, implementar **apenas** os endpoints da secção "FASE 1".
- Estruturar os routers por recurso: `api/clientes.py`, `api/imoveis.py`, etc.
- Toda a lógica de acesso à base de dados passa pelo cliente Supabase em `db/`.
- Os endpoints das Fases 2 e 3 ficam documentados mas não implementados até lá.
