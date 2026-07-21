import asyncio
import csv
import io
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.imovel import ImovelCreate, ImovelUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "imoveis"


def _hoje() -> str:
    return date.today().isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/imoveis")
async def listar_imoveis(
    disponibilidade: Optional[str] = Query(None),
    fonte: Optional[str] = Query(None),
    natureza: Optional[str] = Query(None),
    concelho: Optional[str] = Query(None),
    imovel_ref: Optional[str] = Query(None),
):
    def _fetch():
        q = get_supabase().table(TABLE).select("*").order("data_alteracao", desc=True)
        if disponibilidade:
            q = q.eq("disponibilidade", disponibilidade)
        if fonte:
            q = q.eq("fonte", fonte)
        if natureza:
            q = q.eq("natureza", natureza)
        if concelho:
            q = q.ilike("concelho", f"%{concelho}%")
        if imovel_ref:
            q = q.ilike("imovel_ref", f"%{imovel_ref}%")
        return q.execute()

    resp = await _run(_fetch)
    return resp.data


@router.get("/imoveis/{imovel_ref}")
async def obter_imovel(imovel_ref: str):
    def _fetch():
        return get_supabase().table(TABLE).select("*").eq("imovel_ref", imovel_ref).single().execute()

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")


@router.post("/imoveis", status_code=201)
async def criar_imovel(body: ImovelCreate):
    def _insert():
        data = body.model_dump(exclude_none=True)
        data["data_alteracao"] = _hoje()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/imoveis/{imovel_ref}")
async def atualizar_imovel(imovel_ref: str, body: ImovelUpdate):
    def _update():
        data = body.model_dump(exclude_none=True)
        data["data_alteracao"] = _hoje()
        return get_supabase().table(TABLE).update(data).eq("imovel_ref", imovel_ref).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")
    return resp.data[0]


@router.delete("/imoveis/{imovel_ref}", status_code=204)
async def apagar_imovel(imovel_ref: str):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("imovel_ref", imovel_ref).execute()

    await _run(_delete)


@router.post("/imoveis/import")
async def importar_imoveis_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Ficheiro deve ser .csv")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    campos_texto = {
        "imovel_ref", "natureza", "disponibilidade", "estado", "titulo", "descricao",
        "morada", "codigo_postal", "concelho", "freguesia", "zona",
    }
    campos_numero = {"quartos", "casas_banho", "suites", "num_pisos"}
    campos_decimal = {"area_util", "area_bruta", "area_terreno", "venda_preco", "arrendamento_preco"}
    hoje = _hoje()

    rows = []
    for row in reader:
        if not row.get("imovel_ref", "").strip():
            continue
        record = {"fonte": "csv", "data_alteracao": hoje}
        for campo in campos_texto:
            val = row.get(campo, "").strip()
            if val:
                record[campo] = val
        for campo in campos_numero:
            val = row.get(campo, "").strip()
            if val:
                try:
                    record[campo] = int(val)
                except ValueError:
                    pass
        for campo in campos_decimal:
            val = row.get(campo, "").strip()
            if val:
                try:
                    record[campo] = float(val)
                except ValueError:
                    pass
        rows.append(record)

    if not rows:
        raise HTTPException(status_code=400, detail="CSV sem linhas válidas (falta imovel_ref).")

    def _insert():
        return get_supabase().table(TABLE).upsert(rows, on_conflict="imovel_ref").execute()

    resp = await _run(_insert)
    return {"importados": len(resp.data) if resp.data else 0}
