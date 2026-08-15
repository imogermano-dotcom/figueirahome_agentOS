# Fase — avisar o corretor quando há lead qualificada

## Objectivo

Uma lead que qualifica, ou uma conversa que o A1 escala, deixa de ficar à espera
numa linha de tabela: sai um email para o corretor no momento em que acontece.

## Contexto

Confirmado no código: `guards._promover_lead` e `tools._escalar_para_humano`
acabam ambos num `insert` em `agente_tarefas` e mais nada. Não há notificação de
espécie nenhuma no projecto — nem email, nem WhatsApp, nem push. Se ninguém
abrir o painel, a lead paga que qualificou às 23h fica lá até alguém reparar.

É o último elo do fluxo das leads da Meta: Make escreve → n8n manda template →
lead responde → A1 qualifica → **e agora, o corretor sabe**.

Canal decidido: **email por agora**, outro canal a confirmar depois. O desenho
tem de deixar trocar isso sem mexer nos sítios que notificam.

## Tarefas

1. **`backend/app/notificacoes.py`** — módulo novo, uma função:

   ```python
   def notificar(assunto: str, corpo: str) -> None
   ```

   - **`smtplib` + `email.message` da biblioteca padrão.** Zero dependências
     novas. Um serviço transaccional (Resend, SendGrid) entrega melhor, mas
     obriga a conta e chave; se a entrega vier a ser problema, troca-se o corpo
     desta função e mais nada.
   - **Síncrona de propósito.** `smtplib` bloqueia, e os dois chamadores já
     correm dentro de executores (`_promover_lead` é sync; `_escalar_para_humano`
     usa `_run`). Uma função async obrigaria a contorções nos dois.
   - **Nunca levanta.** `try/except` com `logger.exception`. Isto corre depois
     de a resposta já ter ido para o cliente; falhar a enviar um aviso não pode
     derrubar uma conversa nem impedir a tarefa de ser criada.
   - **Configuração vazia = desligada**, sem erro e sem aviso repetido — mesmo
     padrão do `automacao_secret`. Permite deployar antes de haver credenciais.

2. **`backend/app/config.py`** — `smtp_host`, `smtp_port` (587), `smtp_user`,
   `smtp_password`, `notificacoes_para`. Todos `""` por omissão.

3. **`guards._promover_lead`** — depois de criar a tarefa, `notificar()` com o
   nome, telefone, e os três campos do MQL. É a mensagem que interessa: o
   corretor tem de conseguir ligar sem abrir o painel.

4. **`tools._escalar_para_humano`** — idem, com o motivo e o `URGENTE` no
   assunto quando `inputs["urgente"]`.

5. **Testes** em `backend/tests/` — o valor está nas guardas, não no envio:
   - configuração vazia → não tenta ligar-se a nada e não levanta;
   - falha de SMTP → `_promover_lead` cria a tarefa na mesma e devolve normal;
   - o corpo leva telefone e os campos do MQL (é para isso que serve);
   - assunto ganha `URGENTE` quando escalado como tal.

6. **Documentação** — `docs/decisoes.md`, `CLAUDE.md`, e `backend/.env.example`
   com as chaves novas em `YOUR_*`.

## Ficheiros

| Ficheiro | O quê |
|---|---|
| `backend/app/notificacoes.py` | criar |
| `backend/app/config.py` | 5 settings |
| `backend/app/agents/broker/guards.py` | chamar em `_promover_lead` |
| `backend/app/agents/broker/tools.py` | chamar em `_escalar_para_humano` |
| `backend/tests/test_notificacoes.py` | criar |
| `backend/.env.example`, docs | registo |

## Dependências novas

Nenhuma — `smtplib` e `email.message` são da biblioteca padrão.

## Decisões em aberto

1. **Servidor SMTP e destinatário.** Precisas de me dar o host, a porta, o
   utilizador e para que endereço envia. Se for Gmail, é preciso uma
   *app password* — a palavra-passe normal não serve. Nunca hardcoded: vão para
   Fly.io secrets.
2. **Um destinatário ou vários?** Assumo um endereço; se forem vários,
   `notificacoes_para` aceita lista separada por vírgulas — diz e faço assim.
3. **Notificar também o escalamento, ou só as leads qualificadas?** O plano
   cobre os dois; se preferires só o primeiro, tira-se a tarefa 4.

## Como testar

1. `pytest backend/tests/` a partir de `backend/`.
2. Sem SMTP configurado: correr o fluxo e confirmar que a tarefa é criada e nada
   rebenta — é o estado em que fica até dares as credenciais.
3. Com SMTP: uma lead de teste que qualifique, e confirmar o email com o
   telefone e o orçamento lá dentro.
4. Provocar uma falha de SMTP (password errada) e confirmar que a lead continua
   a ser promovida e a tarefa criada.
