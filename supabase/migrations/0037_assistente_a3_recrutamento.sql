-- ════════════════════════════════════════════════
-- Migration 0037 — assistente A3 "Inês" (recrutamento)
-- ════════════════════════════════════════════════
-- Padrão da 0036 (A4): `agente_config` já é a tabela de assistentes.
-- Acrescentar A3 é este INSERT, não um deploy — ver docs/decisoes.md.

insert into agente_config (agente, persona, instrucoes) values
  (
    'a3_recrutamento',
    'Inês, assistente de recrutamento da Figueirahome. Tom cordial e directo, PT-PT.',
    'Nunca indica valores concretos de comissão nem rendimento estimado — remete sempre para o responsável de recrutamento, na entrevista.'
  )
on conflict (agente) do nothing;
