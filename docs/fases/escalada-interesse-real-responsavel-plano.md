# Escalada = interesse real, e tarefa com responsável (pedido #17, etapas de 28/10, 31/10 e 01/11) — plano

> Plano antes de código. Verificado a 01/11 só em leitura. Sem nomes nem telefones de clientes. Continua `lead-interesse-real-ego-plano.md`.

## O que falha hoje (medido a 01/11)
- `guards._MOTIVO_COMPRA` só apanha `proposta|negoci|visita|oferta|compra`. Das 17 escaladas desde 20/10, **não marcam interesse** (e por isso não criam lead na hora):
  «pedido de informação sobre imóvel», «informação sobre imóvel», «pesquisa de imóvel», «procura de moradia» (×2), «pedido de chamada telefónica».
  Quem escala é um comprador que a Matilde já prometeu que a consultora ia contactar.
- As **17** tarefas `escalar` desde 20/10 têm `agente_tarefas.responsavel` nulo, mesmo com `imovel_ref` (o campo existe e a tabela `imoveis` tem o `angariador` pelo nome do eGO).
- A rede do portal (`meta-leads-rede`) tapa o buraco: compradores Meta com `ego_lead_em` 118 de 121, só 1 de fora desde 20/10. Serve até a regra estar certa.

## Desenho (3 mudanças pequenas, todas em código, nada decidido pelo modelo)

1. **Escalada de comprador conta sempre.** Em `_escalar_para_humano`, tirar o filtro `_MOTIVO_COMPRA` e manter só a exclusão `_MOTIVO_FORA` (recrutamento, angariação, reclamação, legal). `marcar_interesse_real` continua a só marcar contactos Meta **compradores**, por isso recrutamento e angariação nunca entram por aqui. Efeito: a lead sai na volta seguinte do cron (≤ 10 min, 9h–20h), com o motivo no OBS.
2. **«Pediu informação do imóvel» conta.** Quando a Matilde chama `ficha_imovel` para um comprador Meta (localização, preço, fotos, mais informação) marca-se interesse real, motivo `pedido de informação do imóvel`. É o sinal que o pedido de 28/10 (b) descreve, apanhado pela ferramenta e não por palavras. Quem só diz «sim» ao template não chama `ficha_imovel`, por isso não marca.
   ⚠️ Inverte a decisão de 25/10 («perguntar o preço não é interesse real»). É o que o Miguel pede.
3. **Tarefa de escalada com responsável.** `_escalar_para_humano` grava `agente_tarefas.responsavel` = `imoveis.angariador` do `imovel_ref` (o mesmo nome que o eGO escreve), quando o imóvel existe e tem angariador. Sem imóvel ou sem angariador fica nulo, como hoje. O ramo «atualização da escalada» não muda o responsável.

## Fora deste plano (precisa de outra decisão ou de outro sítio)
- **Responsável nas leads Meta** (1/11): `leads.responsavel` (0 de 430) e `contactos.responsavel` (22 de 325) escrevem-se à entrada, no n8n e nos RPCs `lead_meta_*`, que estão fora do repo. Plano à parte.
- **Buscar ao eGO o imóvel que falta à entrada** (31/10 b): depende do #45 (1.ª passagem dos 705 imóveis, por autorizar). O FH2588 já está em `imoveis`.
- **Lead sem consultora** (31/10 a): hoje `SemConsultora` não cria a lead («sem responsável fica invisível no eGO», decisão de 21/10). O Miguel pede «criar com a ref em falta e avisar por email». Ver D4.

## Decisões (tuas)
- **D1** — `ficha_imovel` como sinal de interesse (mudança 2): sim / não / só se a pessoa responder depois.
- **D2** — escalada de comprador sempre conta (mudança 1): confirmar. Inclui «Elegibilidade para Garantia Pública e crédito», que é compra.
- **D3** — `responsavel` da tarefa = `angariador` do imóvel (mudança 3): confirmar o texto igual ao do eGO.
- **D4** — sem consultora: manter «nunca se cria» e acrescentar o email de aviso (proposta), ou criar a lead sem atribuição como o Miguel pediu.
- **D5** — retroativo das 17 tarefas sem responsável e das 4 escaladas que não marcaram: só daqui em diante (proposta), as leads já foram repostas à mão pelo Miguel.

## Testes
- `motivo_de_compra` deixa de ser gate da escalada; recrutamento, angariação, reclamação e legal continuam fora.
- Escalar com motivo «informação sobre imóvel» marca o contacto comprador; contacto de recrutamento não marca.
- `ficha_imovel` de um comprador Meta marca uma vez (os seguintes acrescentam ao resumo); sem contacto Meta, não faz nada e não levanta.
- `_escalar_para_humano` grava `responsavel` do angariador; sem imóvel/angariador deixa nulo.

## Risco
Baixo: `marcar_interesse_real` nunca levanta, só marca e o cron (já testado) cria. O risco real é criar leads a mais para quem só perguntou o preço (D1), mas o cron deduplica contra o eGO e a consultora já recebe estas conversas.

**Estado: plano escrito a 01/11. Por fazer: as tuas decisões D1–D5, código, testes, deploy (com ordem tua).**
