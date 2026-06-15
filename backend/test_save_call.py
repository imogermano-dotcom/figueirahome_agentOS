"""Teste isolado de save_call: Claude extracção + Supabase upsert."""
import asyncio
from datetime import datetime

from app.agents.voice.save_call import save_call
from app.agents.voice.session import CallSession


async def main():
    session = CallSession(
        call_control_id="test-manual-001",
        numero_origem="+351912345678",
        iniciada_em=datetime.utcnow(),
    )
    session.transcricao_acumulada = (
        "Agente: Olá! Obrigada por contactar a Figueirahome. Em que posso ajudá-lo?\n"
        "Cliente: Bom dia, chamo-me João Ferreira. Estou à procura de um apartamento para comprar em Figueira da Foz.\n"
        "Agente: Que tipo de apartamento procura e qual é o seu orçamento?\n"
        "Cliente: Prefiro T2 ou T3, orçamento até 180 mil euros. O meu telefone é 912 345 678.\n"
        "Agente: Perfeito, vou registar os seus dados. Obrigada pelo contacto!\n"
    )

    print("A chamar save_call com transcrição real...")
    await save_call(session)
    print("Concluído. Verifica Supabase → tabelas clientes, chamadas, leads.")


if __name__ == "__main__":
    asyncio.run(main())
