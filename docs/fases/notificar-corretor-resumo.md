# Resumo — avisar o corretor (2026-08-15)

Plano: `docs/fases/notificar-corretor-plano.md`. Decisões: `docs/decisoes.md`,
secção "Notificações ao corretor".

## O que ficou a funcionar

Uma lead que qualifica, ou uma conversa que o A1 escala, deixa de ficar só numa
linha de tabela: sai email para o corretor no momento em que acontece.

| Ficheiro | O quê |
|---|---|
| `backend/app/notificacoes.py` | `notificar(assunto, corpo)`, `configurado()`, `destinatarios()`, `demo()` |
| `backend/app/config.py` | `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `notificacoes_para` |
| `guards._promover_lead` | avisa com nome, telefone, email e os três campos do MQL |
| `tools._escalar_para_humano` | avisa com motivo, contacto, imóvel e resumo; `URGENTE` no assunto quando é o caso |
| `tests/test_notificacoes.py` + 1 em `test_leads_meta.py` | 6 testes — **81 verdes** |

Zero dependências novas: `smtplib` e `email.message` são da biblioteca padrão.

## Está deployável já, e inerte

Com `SMTP_HOST` ou `NOTIFICACOES_PARA` vazios, `configurado()` devolve `False` e
`notificar()` sai sem tentar abrir ligação nenhuma. Não é erro — é o estado
normal até haver credenciais, e ligar depois **não exige novo deploy**, só pôr
os secrets.

## Por fazer

- **Credenciais SMTP**: host, porta, utilizador, password e destinatário. Gmail
  exige *app password*, não a normal. Vão para Fly.io secrets:
  ```
  flyctl secrets set SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... NOTIFICACOES_PARA=... --app figueirahome-agentos
  ```
- **Deployar o backend** para o código entrar.
- **Confirmar o canal definitivo** — email foi decidido como "por agora". Quando
  mudar, muda-se o corpo de `notificar()`; os dois sítios que chamam não mexem.

## Como testar

1. `pytest backend/tests/` de `backend/` — 81 verdes.
2. `python -m app.notificacoes` de `backend/` — auto-verificação das guardas.
3. Sem SMTP: correr o fluxo e confirmar que a tarefa é criada e nada rebenta.
4. Com SMTP: lead de teste que qualifique → email com telefone e orçamento.
5. Password errada de propósito → a lead é promovida e a tarefa criada na mesma.
