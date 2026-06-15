import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.imovel import ImovelCreate, ImovelUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "agente_imoveis"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/imoveis")
async def listar_imoveis(
    estado: Optional[str] = Query(None),
    fonte: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    localizacao: Optional[str] = Query(None),
):
    def _fetch():
        q = get_supabase().table(TABLE).select("*").order("criado_em", desc=True)
        if estado:
            q = q.eq("estado", estado)
        if fonte:
            q = q.eq("fonte", fonte)
        if tipo:
            q = q.eq("tipo", tipo)
        if localizacao:
            q = q.ilike("localizacao", f"%{localizacao}%")
        return q.execute()

    resp = await _run(_fetch)
    return resp.data


@router.get("/imoveis/{imovel_id}")
async def obter_imovel(imovel_id: UUID):
    def _fetch():
        return get_supabase().table(TABLE).select("*").eq("id", str(imovel_id)).single().execute()

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")


@router.post("/imoveis", status_code=201)
async def criar_imovel(body: ImovelCreate):
    def _insert():
        data = body.model_dump(exclude_none=True)
        data["criado_em"] = _now()
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/imoveis/{imovel_id}")
async def atualizar_imovel(imovel_id: UUID, body: ImovelUpdate):
    def _update():
        data = body.model_dump(exclude_none=True)
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).update(data).eq("id", str(imovel_id)).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")
    return resp.data[0]


@router.delete("/imoveis/{imovel_id}", status_code=204)
async def apagar_imovel(imovel_id: UUID):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("id", str(imovel_id)).execute()

    await _run(_delete)


@router.post("/imoveis/import")
async def importar_imoveis_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Ficheiro deve ser .csv")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    campos_validos = {"referencia", "tipo", "localizacao", "preco", "area", "quartos", "descricao", "estado"}
    rows = []
    now = _now()

    for row in reader:
        record = {"fonte": "csv", "criado_em": now, "atualizado_em": now}
        for campo in campos_validos:
            val = row.get(campo, "").strip()
            if val:
                if campo in ("preco", "area"):
                    try:
                        record[campo] = float(val)
                    except ValueError:
                        pass
                elif campo == "quartos":
                    try:
                        record[campo] = int(val)
                    except ValueError:
                        pass
                else:
                    record[campo] = val
        rows.append(record)

    if not rows:
        raise HTTPException(status_code=400, detail="CSV sem linhas válidas.")

    def _insert():
        return get_supabase().table(TABLE).insert(rows).execute()

    resp = await _run(_insert)
    return {"importados": len(resp.data) if resp.data else 0}
