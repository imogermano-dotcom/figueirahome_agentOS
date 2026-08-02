# eGO Real Estate — Scraper Portátil (Login + Export Relatórios)

Documento p/ import noutro projecto. Baseado em `egorealestate/scripts/access-admin.js` + `export-oportunidades.js` (JMWAIweb), generalizado p/ qualquer módulo/relatório/período.

## Stack

- Node.js + Playwright (`npm i playwright dotenv`)
- `.env`: `EGOREALESTATE_EMAIL`, `EGOREALESTATE_PASSWORD`
- Sessão persistente via `storageState` (evita novo login em cada run)

## Mecanismo core

### 1. Login (uma vez, sessão fica gravada)

- Vai a `https://admin.egorealestate.com/`
- Deteta form de login (`input[type=email]`, `input[type=password]`, botão submit/"Entrar")
- Preenche + submete com credenciais do `.env`
- Se sem credenciais: deixa browser aberto p/ login manual (banner + highlight nos campos), espera navegação
- Após login: `context.storageState({ path: AUTH_FILE })` — grava cookies/localStorage p/ reuso
- Runs seguintes: `chromium.newContext({ storageState: AUTH_FILE })` — pula login

### 2. Navegação até ao módulo

URL directa ao módulo (ex: `/egocore/leads` p/ Oportunidades). Cada módulo eGO tem o seu path — descobrir navegando manualmente uma vez e copiando o URL.

### 3. Filtros (via `dispatchEvent`, não `.click()`)

**Importante:** a UI do eGO só reage a `dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}))` disparado manualmente — `.click()` normal do Playwright não activa os handlers JS deles em muitos elementos (tags de filtro sidebar).

Padrão: sem selectors CSS estáveis → matching por `textContent`:

```js
await page.evaluate(() => {
  const el = Array.from(document.querySelectorAll('span.sideTag'))
    .find(e => e.textContent.trim() === 'NOME_DO_FILTRO'); // parametrizar
  if (!el) return false;
  const target = el.querySelector('a') || el;
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  return true;
});
```

Generalizar: extrair `NOME_DO_FILTRO` (ex: período "Últimos 3 dias", "Este mês") e o filtro base (ex: remover "Minhas X") como parâmetros da função.

### 4. Seleccionar todos os registos filtrados

```js
await page.evaluate(() => document.querySelector('.btDeselectAll, a.btDeselectAll')?.click());
await page.evaluate(() => document.querySelector('.btSelectAll, a.btSelectAll')?.click());
```

(Estes dois respondem a `.click()` normal — só as sideTags precisam `dispatchEvent`.)

### 5. Abrir menu Relatórios

```js
await page.evaluate(() => {
  const el = Array.from(document.querySelectorAll('a'))
    .find(e => e.textContent.trim() === 'Relatórios' && e.getAttribute('onclick')?.includes('popupreports'));
  if (el) { el.click(); return true; }
  return false;
});
```

Nota: link "Relatórios" tem `onclick` próprio, `.click()` normal funciona aqui (ao contrário das sideTags).

### 6. Escolher relatório guardado + capturar download

```js
await page.evaluate((reportName) => {
  const items = Array.from(document.querySelectorAll('#ReportsList .popupReportItem, #ReportsPopup .popupReportItem'));
  const item = items.find(el => el.textContent.trim() === reportName);
  if (item) { (item.querySelector('a') || item).click(); return true; }
  return false;
}, REPORT_NAME); // parametrizar — nome do relatório guardado no eGO
```

Download capturado via listener, não parsing de DOM/tabela:

```js
let downloadPath = null;
context.on('download', async download => {
  downloadPath = path.join(OUTPUT_DIR, download.suggestedFilename());
  await download.saveAs(downloadPath);
});
// depois do click no relatório: esperar até 30s por downloadPath
```

## Como generalizar p/ novo projecto

Função devia aceitar como parâmetros:

| Param | Exemplo | Onde entra |
|---|---|---|
| `moduleUrl` | `/egocore/leads` | passo 2 |
| `filterToRemove` | `'Minhas oportunidades'` (opcional) | passo 3 |
| `periodFilter` | `'Últimos 3 dias'` | passo 3 |
| `reportName` | `'teste_jmarques'` | passo 6 |
| `outputDir` | caminho local | download |

Relatório tem de já existir gravado no eGO (feito manualmente na UI uma vez) — o script só o dispara, não cria relatórios novos.

## Gotchas conhecidos

- Sessão expira → apagar `auth/session.json`, correr login de novo
- `.click()` falha silenciosamente nas sideTags — usar sempre `dispatchEvent(MouseEvent)` nesses
- Evitar menu "..." ao lado de "Imprimir" — item seguinte é "Apagar" (delete), risco de erro de permissão se calhar mal
- `headless:false` + `slowMo` recomendado em dev — UI tem race conditions se for rápido demais; subir p/ `headless:true` só depois de validado
- `waitUntil:'networkidle'` no goto inicial — eGO é SPA-ish, carrega afinal chamadas async

## Ficheiros de origem (JMWAIweb, para referência)

- `egorealestate/scripts/access-admin.js` — login + sessão
- `egorealestate/scripts/export-oportunidades.js` — export completo (implementação concreta do módulo Oportunidades)
