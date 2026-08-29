"""Lead não qualificada, de qualquer origem — tabela `leads` (migration 0021).

Substituiu `agente_leads` a 2026-08-18. A tabela antiga tinha 4 campos úteis
(`cliente_id`, `imovel_id`, `estado`, `notas`) e nenhum contacto próprio: o nome
e o telefone vinham sempre por join a `agente_clientes`. Isso funcionava para as
leads nascidas numa conversa, e deixava as 119 da Meta — que trazem nome e
telefone no formulário e nunca chegam a ter `cliente_id` — invisíveis no painel.

Em `leads` o contacto está na própria linha e `cliente_id` é opcional. Os dois
casos coexistem, e é o painel que decide qual mostrar.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

# União dos dois vocabulários que existiam. O de `leads` (0021) manda porque é
# dele que `guards._ESTADOS_LEAD_ABERTA` depende; `visita` e `proposta` vêm do
# painel antigo e são etapas comerciais reais que não havia razão para perder.
#
# `sem_resposta` e `engano` são os desfechos da spec §2.2 que faltavam. Nenhum
# precisa de migration: a `0021` descreve os estados num comentário, não numa
# CHECK constraint.
ESTADOS = (
    "nova", "contactada", "sem_resposta", "qualificada",
    "visita", "proposta",
    "fechada", "perdida", "sem_interesse", "engano",
)

# Fechadas para o assistente: uma lead nestes estados não volta a ser reaberta
# nem requalificada (`tools._criar_lead_se_preciso`).
#
# `sem_resposta` **não** está aqui de propósito — significa "desistimos de
# insistir", não "não falar com esta pessoa". Quem responde uma semana depois tem
# de continuar a cair na A1 com o `imovel_ref` do anúncio; fechá-lo fazia
# `guards.lead_aberta` devolver None e a pessoa chegava ao A2 sem contexto.
ESTADOS_FECHADOS = ("fechada", "perdida", "sem_interesse", "engano")

# Eixo distinto de `tipo` (o interesse: compra | angariacao).
ORIGENS = ("meta", "assistente", "voz", "landing", "manual")


class LeadBase(BaseModel):
    tipo: Optional[str] = None
    estado: Optional[str] = None
    origem: Optional[str] = None

    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

    imovel_ref: Optional[str] = None
    responsavel: Optional[str] = None
    notas: Optional[str] = None
    cliente_id: Optional[UUID] = None


class LeadCreate(LeadBase):
    estado: str = "nova"
    origem: str = "manual"
    tipo: str = "compra"


class LeadUpdate(LeadBase):
    # Booleano e não o carimbo `contacto_humano_em` (migration 0032), por duas
    # razões independentes:
    #
    # 1. `atualizar_lead` faz `model_dump(exclude_none=True)` — um None nunca
    #    chega à base. Com um campo `datetime`, marcar funcionava e DESMARCAR
    #    não, e uma consultora marcada por engano ficava marcada para sempre.
    #    `False` não é `None`: sobrevive ao filtro e limpa a coluna.
    # 2. A hora é do servidor. O browser não tem de decidir quando é agora.
    #
    # Só no update: uma lead que nasce já contactada por uma pessoa não passa
    # por esta página.
    contacto_humano: Optional[bool] = None


class Lead(LeadBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime
    contacto_humano_em: Optional[datetime] = None

    model_config = {"from_attributes": True}
