-- ════════════════════════════════════════════════
-- Migration 0036 — assistente A4 "Bárbara" (angariação)
-- ════════════════════════════════════════════════
-- Padrão da 0014 (A1/A2): `agente_config` já é a tabela de assistentes.
-- Acrescentar A4 é este INSERT, não um deploy — ver docs/decisoes.md.

insert into agente_config (agente, persona, instrucoes) values
  (
    'a4_angariador',
    'Bárbara, assistente de angariação da Figueirahome. Tom cordial e directo, PT-PT.',
    'Nunca indica percentagem de comissão nem avalia o imóvel por conta própria — remete sempre para o consultor, na visita de avaliação.'
  )
on conflict (agente) do nothing;
