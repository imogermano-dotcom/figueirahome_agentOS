# Fase 4c — Resumo: RLS Supabase

**Data:** 2026-06-15  
**Estado:** ✅ Concluída (migration criada; aplicar no Supabase dashboard)

---

## O que ficou feito

- `supabase/migrations/0003_rls.sql` — RLS activado nas 6 tabelas `agente_*`
- Política `auth_full_access` (authenticated → tudo permitido) em cada tabela
- `anon` bloqueado por defeito (sem política = sem acesso)
- `service_role` (backend FastAPI) bypassa RLS automaticamente — zero impacto

## Ficheiros alterados

| Ficheiro | Alteração |
|---|---|
| `supabase/migrations/0003_rls.sql` | Criado |
| `docs/database-schema.md` | Secção RLS actualizada com estado activo |
| `CLAUDE.md` | Fase 4c marcada ✅, próximos passos actualizados |

## Como aplicar

1. Abrir Supabase dashboard → SQL Editor
2. Colar e executar o conteúdo de `supabase/migrations/0003_rls.sql`
3. Verificar:

```sql
select relname, relrowsecurity
from pg_class
where relname like 'agente_%'
order by relname;
```

Todas as 6 linhas devem ter `relrowsecurity = true`.

## Notas

- Migration `0003` **não** entra em conflito com `0001`/`0002` (já aplicadas).
- RLS não afecta webhooks Telnyx/Meta — usam backend com service_role.
- Política pode ser refinada no futuro (ex: por utilizador/agência) sem breaking changes.
