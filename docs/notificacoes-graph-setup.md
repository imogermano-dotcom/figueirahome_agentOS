# Notificações por email — configuração passo a passo

Como pôr a funcionar o aviso ao director comercial e à consultora do imóvel,
via Microsoft Graph. Do zero até email recebido.

**Porquê Graph e não SMTP**: o correio da agência é Microsoft 365 e a Microsoft
está a extinguir o SMTP AUTH no Exchange Online. Ver `docs/decisoes.md`.

---

## 1. Registar a aplicação no Entra ID

**portal.azure.com** → **Microsoft Entra ID** → **Registos de aplicações** →
**Novo registo**

| Campo | Valor |
|---|---|
| Nome | `figueirahome-agentos-mail` |
| Tipos de conta suportados | Contas apenas neste diretório organizacional (inquilino único) |
| URI de redirecionamento | **deixar vazio** |

O URI fica vazio porque não há utilizador a autenticar-se: é a aplicação a falar
por si (*client credentials*).

Depois de criar, na página **Descrição geral**, anotar:

- **ID do aplicativo (cliente)** → será o `GRAPH_CLIENT_ID`
- **ID do diretório (locatário)** → será o `GRAPH_TENANT_ID`

## 2. Dar a permissão de envio

**Permissões de API** → **Adicionar uma permissão** → **Microsoft Graph**

→ **Permissões de aplicativo** ⚠️ **não** "Permissões delegadas".

É o erro mais comum. Delegadas exigem um utilizador com sessão iniciada; o
backend não tem nenhum.

Procurar **`Mail.Send`** → seleccionar → **Adicionar permissões**.

Depois: **Conceder consentimento de administrador para \<organização\>** →
confirmar.

✅ A linha do `Mail.Send` tem de ficar com **"Concedido para \<organização\>"**
a verde. Se ficar um triângulo de aviso, o consentimento não foi dado e o envio
falha com `403`.

O `User.Read` que vem por omissão pode ser removido — não serve aqui.

## 3. Criar o segredo

**Certificados e segredos** → **Novo segredo do cliente** → descrição e validade.

⚠️ **O segredo expira** — a Azure já não permite segredos permanentes. Escolher
24 meses e **apontar a data**: quando expirar, as notificações param sem aviso
nenhum e o log mostra `401`.

Copiar o **Valor** de imediato. Sai da página e deixa de ser visível; só resta
criar outro.

## 4. Escolher o remetente

Uma mailbox **com licença** do tenant — é o endereço que aparece como remetente.
Pode ser uma caixa dedicada (`avisos@figueirahome.pt`) ou uma existente.

Não precisa de ser a mesma que recebe.

## 5. Testar localmente, antes de tocar em produção

Em `backend/.env` (está no `.gitignore`):

```
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...
GRAPH_CLIENT_SECRET=...
GRAPH_REMETENTE=avisos@figueirahome.pt
NOTIFICACOES_PARA=miguel.germano@figueirahome.pt
```

E a partir de `backend/`:

```bash
python -c "import sys; sys.path.insert(0,'.'); from app.notificacoes import notificar; notificar('Teste FigueiraHome', 'Se recebeste isto, a Graph está configurada.')"
```

Silêncio = enviado. Qualquer erro aparece no log com a mensagem da Graph.

Testar aqui primeiro separa "as credenciais estão bem" de "o deploy está bem".

## 6. Pôr em produção

```
C:\Users\joaoa\.fly\bin\flyctl.exe secrets set `
  GRAPH_TENANT_ID=... `
  GRAPH_CLIENT_ID=... `
  GRAPH_CLIENT_SECRET=... `
  GRAPH_REMETENTE=... `
  NOTIFICACOES_PARA=miguel.germano@figueirahome.pt `
  --app figueirahome-agentos
```

O `secrets set` reinicia a máquina sozinho. O **código** precisa de deploy.

## 7. Testar ponta a ponta

Uma lead de teste num imóvel com angariadora mapeada (ex. `FH2581`, Alexandra
Santos), responder no WhatsApp, e confirmar que chegam **dois** destinatários:
o director e a consultora.

---

## Erros e o que significam

| Erro | Causa |
|---|---|
| `403 Insufficient privileges` | falta o consentimento de administrador (passo 2) |
| `403 Access is denied ... ApplicationAccessPolicy` | há uma política a restringir e a mailbox não está incluída |
| `404 MailboxNotEnabledForRESTAPI` | o `GRAPH_REMETENTE` não tem licença ou não é mailbox real |
| `401 AADSTS7000215` | segredo errado — copiou-se o *ID* em vez do *Valor* |
| `400 AADSTS90002` | tenant errado |
| `401` de repente, meses depois | o segredo expirou (passo 3) |

Nenhum destes derruba nada: `notificar()` engole os erros e a tarefa em
`agente_tarefas` continua a ser criada. Ficam no log do Fly.

## Apertar depois (opcional)

`Mail.Send` de aplicação permite enviar **como qualquer mailbox do tenant**. Para
restringir a uma só, no Exchange Online PowerShell:

```powershell
New-ApplicationAccessPolicy -AppId <CLIENT_ID> `
  -PolicyScopeGroupId avisos@figueirahome.pt `
  -AccessRight RestrictAccess `
  -Description "Só a caixa de avisos do agentOS"
```

Não bloqueia nada agora; vale a pena depois de estar a funcionar.
