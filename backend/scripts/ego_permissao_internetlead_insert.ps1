# Liga (ou desliga) a permissão internetlead/insert (id 483) ao utilizador da API na agência Figueira Home.
# Corre no TEU terminal (PowerShell). Altera segurança no eGO: só com ordem expressa do dono da conta.
#
#   .\ego_permissao_internetlead_insert.ps1 -DoEnv      # só mostra o estado, com as credenciais do backend\.env (sem escrever nada)
#   .\ego_permissao_internetlead_insert.ps1              # só mostra o estado (leitura), a pedir utilizador e palavra-passe
#   .\ego_permissao_internetlead_insert.ps1 -Ligar       # liga a 483
#   .\ego_permissao_internetlead_insert.ps1 -Desligar    # desliga a 483
#
# A palavra-passe é pedida no ecrã (não fica em ficheiro, histórico nem log) e o token nunca é impresso.
# Não usa DeleteAllSecurityUserPermissions. Depois de ligar, reiniciar a app (token novo): ver docs/eGO-api/ego-api.md.

param(
    [switch]$Ligar,
    [switch]$Desligar,
    [switch]$DoEnv,   # lê EGOREALESTATE_CRM_USERNAME/PASSWORD do backend\.env (as que o backend já usa); nunca as imprime
    [string]$Utilizador = $env:EGO_UTILIZADOR,
    [string]$Escritorio = "FIGUEIRAHOME",
    [int]$FuncionalidadeId = 483
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # acentos certos no ecrã
$base = "https://api.egocrm.com"
# A Cloudflare do eGO recusa pedidos sem User-Agent de browser.
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

if ($Ligar -and $Desligar) { throw "Escolhe só um: -Ligar ou -Desligar." }
$palavraPasse = $null
if ($DoEnv) {
    $envFicheiro = Join-Path $PSScriptRoot "..\.env"
    if (-not (Test-Path $envFicheiro)) { throw "Não encontrei $envFicheiro" }
    foreach ($linha in Get-Content $envFicheiro) {
        if ($linha -match '^\s*EGOREALESTATE_CRM_USERNAME\s*=\s*(.*?)\s*$') { $Utilizador = $Matches[1].Trim('"').Trim("'") }
        if ($linha -match '^\s*EGOREALESTATE_CRM_PASSWORD\s*=\s*(.*?)\s*$') { $palavraPasse = $Matches[1].Trim('"').Trim("'") }
    }
    if (-not ($Utilizador -and $palavraPasse)) { throw "O .env não tem EGOREALESTATE_CRM_USERNAME/PASSWORD." }
} else {
    if (-not $Utilizador) { $Utilizador = Read-Host "Utilizador do eGO (o mesmo do EGOREALESTATE_CRM_USERNAME)" }
    $segura = Read-Host "Palavra-passe do eGO" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try { $palavraPasse = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Dados($resposta) { if ($resposta.data) { $resposta.data } else { $resposta } }

# 1.º passo: login → lista de escritórios; 2.º: login no escritório → token com as permissões dele
$corpo = @{ username = $Utilizador; password = $palavraPasse } | ConvertTo-Json
$palavraPasse = $null
try {
    $p1 = Dados (Invoke-RestMethod -Method Post -Uri "$base/authentication/Authentication/Login" -Body $corpo `
        -ContentType "application/json" -UserAgent $ua)
} catch {
    throw "Login recusado pelo eGO ($($_.Exception.Message)). Utilizador/palavra-passe errados? Tenta com -DoEnv (usa as do backend\.env)."
}
$app = $p1.applicationsAvailable | Where-Object { $_.name -and $_.name.ToUpper() -eq $Escritorio.ToUpper() } | Select-Object -First 1
if (-not $app) { throw "Escritório '$Escritorio' não encontrado na conta." }
$appId = if ($app.id) { $app.id } else { $app.applicationId }

function Entrar {
    $p2 = Dados (Invoke-RestMethod -Method Get -Uri "$base/authentication/Authentication/LoginToApplication?applicationId=$appId" `
        -Headers @{ Authorization = "Bearer $($p1.token)" } -UserAgent $ua)
    return $p2
}
$sessao = Entrar
$utilizadorId = $sessao.securityUserId
$cab = @{ Authorization = "Bearer $($sessao.token)" }

function EstadoDaFuncionalidade($cabecalho) {
    $r = Invoke-RestMethod -Method Get -UserAgent $ua -Headers $cabecalho `
        -Uri "$base/authentication/Authentication/ListSecurityFeaturesShares?applicationId=$appId&securityUserId=$utilizadorId"
    # a lista pode vir direta, embrulhada em `data`, ou desenrolada pelo PowerShell
    $lista = @(if ($r -is [System.Array]) { $r } elseif ($r.data) { $r.data } else { $r })
    $item = $lista | Where-Object { [int]$_.securityFeatureID -eq $FuncionalidadeId } | Select-Object -First 1
    if (-not $item) { return "não encontrada (a lista tem $($lista.Count) itens)" }
    return $item.securityAccessFlag
}

Write-Host "Escritório $Escritorio (applicationId $appId), utilizador $utilizadorId."
Write-Host "Estado atual da funcionalidade ${FuncionalidadeId} (internetlead/insert): $(EstadoDaFuncionalidade $cab)  (1 = ligada, 0 = desligada)"

if (-not ($Ligar -or $Desligar)) { Write-Host "Só leitura: nada alterado."; return }

$flag = if ($Ligar) { "true" } else { "false" }
$acao = if ($Ligar) { "LIGAR" } else { "DESLIGAR" }
$confirma = Read-Host "Vais $acao a funcionalidade $FuncionalidadeId ao utilizador $utilizadorId. Escreve SIM para continuar"
if ($confirma -ne "SIM") { Write-Host "Cancelado."; return }

$q = "securityUserId=$utilizadorId&securityFeatureId=$FuncionalidadeId&securityAccessFlag=$flag&applicationId=$appId"
$resp = Invoke-RestMethod -Method Post -Uri "$base/organization/SecurityUser/InsertSecurityUserPermissions?$q" -Headers $cab -UserAgent $ua
Write-Host "Resposta do eGO: $resp"

# As permissões vão no token: novo login antes de confirmar
$sessao = Entrar
$cab = @{ Authorization = "Bearer $($sessao.token)" }
Write-Host "Estado depois: $(EstadoDaFuncionalidade $cab)  (esperado: $(if ($Ligar) { 1 } else { 0 }))"
Write-Host "Falta reiniciar a figueirahome-agentos para o backend fazer login novo."
