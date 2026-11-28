# Registo do Miguel — atualizações de 28/11/2026

Notas curtas por pedido. Sem nomes nem telefones de pessoas.

## #17 — Criar a lead no eGO no momento em que entra (reaberto)
- **Estado:** **Em curso** · **Com quem está:** Developer (ver a 1.ª lead real).
- **Nota (Developer):** 28/11 Claude: a lead de compra da Meta passa a ser criada no eGO **assim que entra**, a qualquer hora, sem esperar 2 h nem a conversa. Antes, uma lead que não respondia só chegava ao eGO 2 h depois (a de 28/11 00:24 só foi criada às 02:30). Agora o n8n chama o nosso servidor logo a seguir a gravar a lead e **antes** do template, e uma falha nessa chamada não trava o envio do template; se falhar, recebes um email de alerta com o id da lead.
- **Quem aceita e quem recusa o WhatsApp** são tratados no mesmo sítio: a recusa também é criada na entrada, com a nota «recusou o WhatsApp: contactar por telefone, nunca por WhatsApp». O email ao Miguel e à consultora quando alguém recusa mantém-se, agora com o resultado real da criação. Antes havia duas vias (a da recusa a passar duas vezes pela criação).
- **Regras que se mantêm:** nunca se cria sem consultora responsável nem sem email (o alerta diz «criar à mão»); se a pessoa já tem oportunidade ativa do mesmo imóvel ou a lead já está na caixa, não se cria outra e a consultora é avisada; uma repetição do webhook da Meta não cria 2.ª lead. O cron das 2 h fica como rede de segurança.
- **A lead entra sem conversa.** A nota da lead diz «acabou de entrar: a Matilde vai contactá-la por WhatsApp». A conversa a seguir como notas da lead (fases 2 e 3) **ainda não está feita**.
- **Feito:** commits `c38feff`, `bed3dd9`; `LEAD_ENTRADA_EGO=1` ligado a 28/11. Plano: `lead-meta-a-entrada-plano.md`.
- **Por ver:** a 1.ª lead real depois de ligado: criada ao segundo, consultora e imóvel certos no eGO, sem duplicado do cron das 2 h, e o email da recusa a dizer «Lead criada no eGO».
- **Pergunta ao Miguel:** as consultoras preferem que a lead que acabou de entrar já apareça no eGO mesmo sem a pessoa ter respondido? Se não, desligamos com um interruptor (`LEAD_ENTRADA_EGO`) e volta o cron das 2 h.
