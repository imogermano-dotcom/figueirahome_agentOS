# Escalada sempre «URGENTE» (pedido #20, urgência passada a alta, 25/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes nem telefones de clientes.

## Pedido
O Miguel passou a urgência do #20 a **alta**: o aviso imediato por email (a ele e à consultora) quando a mensagem precisa de uma pessoa
deve chegar como urgente. Critério escolhido a 25/11: **sempre**, qualquer escalada.

## Estado medido (25/11, só leitura)
- A etapa de 21/11 (aviso imediato, rede em código, consultoras do telefone) está em produção desde 23/11, mas **0 escaladas reais desde então** (a última foi a 21/11). Só há o ensaio de 24/11.
- A única urgência no código é o campo opcional `urgente` do `escalar_para_humano` (`tools.py:175`, «reclamações e assuntos legais»). Só põe o prefixo «URGENTE — » no título da tarefa e no assunto do email (`tools.py:894` e `:932`).
- Nada mais o define: a rede em código (`engine._escalar_se_precisa`, `engine.py:431`) nunca o passa. A confirmação de visita do CAP_21715 sairia **sem** o prefixo.

## Desenho
1. `tools._escalar_para_humano`: o prefixo «URGENTE — » passa a ser **constante** nos dois sítios (tarefa nova e email de atualização da escalada). Deixa de depender do modelo.
2. Tirar `urgente` do esquema da tool (`tools.py:175`) e do que o lê: o modelo já não decide, e um campo que não faz nada engana. Se `urgente` estiver numa allowlist de inputs seguros (`_TOOLS_INPUT_SEGURO`), ajustar o teste que a vigia.
3. Sem mudança no motor: a rede em código chama a mesma `escalar_para_humano`, por isso herda o prefixo.
4. Sem coluna nova: a «prioridade» é o prefixo no título e no assunto do email. Migration nenhuma.

## Efeito a ter presente
«Sempre» inclui as escaladas **da Inês e da Bárbara** (entrevista de recrutamento, angariação, venda), que hoje são de rotina. O prefixo deixa de distinguir o que é mesmo urgente. Se o ruído incomodar, o ajuste é um `if` no agente (só A1/A2) e fica em 1 linha. A combinar com o Miguel depois de ver o primeiro mês.

## Testes
- Escalada normal: título da tarefa e assunto do email começam por «URGENTE — ».
- Atualização de escalada já registada: o assunto também.
- Rede em código (mensagem que `guards.precisa_de_pessoa` apanha, sem tool do modelo): o email e a tarefa saem com o prefixo.
- Esquema da tool sem `urgente`.

## Passos (cada um com OK próprio)
1. Código e testes, sem commit.
2. Commit e push.
3. Deploy do `figueirahome-agentos`.
4. Nota ao Miguel no registo (#20) e atualizar o CLAUDE.md.
5. Ver a 1.ª escalada real depois do deploy: assunto do email, destinatários, consultora da tarefa.

## O que não muda
Nada se escreve no eGO. Os destinatários (Miguel + consultoras do telefone) e a regra de o follow-up parar depois de escalar ficam iguais.
