# Fase 4c — RLS Supabase

## Objectivo

Activar Row Level Security em todas as tabelas `agente_*`, bloqueando acesso anónimo directo à DB. Backend (service_role) não é afectado.

---

## Contexto e segurança

| Caller | Chave | RLS |
|---|---|---|
| Backend FastAPI | `service_role_key` | **Bypass automático** — zero impacto |
| Frontend (via FastAPI) | JWT Supabase (Auth) | Não acede DB directamente |
| Webhook Telnyx / Meta | Usa backend | **Bypass automático** |
| Acesso anónimo directo | `anon` key | **Bloqueado** após RLS ✅ |

Activar RLS não quebra nada no sistema actual.

---

## Tarefas

1. Criar `supabase/migrations/0003_rls.sql` — enable RLS + políticas para `authenticated`
2. Actualizar `docs/database-schema.md` — marcar RLS como activo
3. Aplicar migration no Supabase (instruções para o utilizador)
4. Actualizar `CLAUDE.md` — marcar Fase 4c concluída
5. Escrever `docs/fases/fase4c-resumo.md`

---

## Ficheiros a criar/alterar

- `supabase/migrations/0003_rls.sql` ← novo
- `docs/database-schema.md` ← actualizar secção RLS
- `CLAUDE.md` ← marcar Fase 4c ✅
- `docs/fases/fase4c-resumo.md` ← novo

---

## Dependências novas

Nenhuma.

---

## Decisões em aberto

Nenhuma. Padrão já definido no `database-schema.md`:
- `service_role` bypassa RLS (Supabase default)
- `authenticated` → acesso total
- `anon` → bloqueado

---

## SQL da migration

```sql
-- Tabelas: agente_clientes, agente_imoveis, agente_leads,
--          agente_chamadas, agente_conversas, agente_config

-- ENABLE RLS
alter table agente_clientes enable row level security;
alter table agente_imoveis  enable row level security;
alter table agente_leads    enable row level security;
alter table agente_chamadas enable row level security;
alter table agente_conversas enable row level security;
alter table agente_config   enable row level security;

-- POLÍTICAS: authenticated pode tudo
create policy "auth_full_access" on agente_clientes
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_imoveis
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_leads
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_chamadas
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_conversas
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_config
  for all to authenticated using (true) with check (true);
```

---

## Como testar

No Supabase dashboard → Table Editor → tenta aceder a `agente_clientes` sem auth → deve retornar 0 rows (ou erro).

Verificação via SQL Editor:
```sql
select relname, relrowsecurity
from pg_class
where relname like 'agente_%';
-- relrowsecurity = true em todas as tabelas ✅
```

---

## Sem decisões em aberto — podes aprovar directamente.
