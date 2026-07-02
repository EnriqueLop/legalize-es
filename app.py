"""
Consultor Legislativo España – backend FastAPI
Lee los documentos del repositorio legalize-es y expone endpoints de
búsqueda y consulta con IA (Claude).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from pathlib import Path
from typing import List, Optional

import yaml
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import documents
import llm

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

REPO_PATH     = Path(__file__).parent
SEMANTIC_POOL = 60   # candidatos keyword que se re-ordenan semánticamente
INDEX_CACHE = Path("/tmp/legalize_index.json")
MAX_RESULTS = 30
PREVIEW_CHARS = 400

REGIONS: dict[str, str] = {
    "es": "España (Estatal)",
    "es-an": "Andalucía",
    "es-ar": "Aragón",
    "es-as": "Asturias",
    "es-cb": "Cantabria",
    "es-cl": "Castilla y León",
    "es-cm": "Castilla-La Mancha",
    "es-cn": "Canarias",
    "es-ct": "Cataluña",
    "es-ex": "Extremadura",
    "es-ga": "Galicia",
    "es-ib": "Islas Baleares",
    "es-mc": "Murcia",
    "es-md": "Madrid",
    "es-nc": "Navarra",
    "es-pv": "País Vasco",
    "es-ri": "La Rioja",
    "es-vc": "Valencia",
}

RANK_LABELS: dict[str, str] = {
    "ley": "Ley",
    "ley_organica": "Ley Orgánica",
    "real_decreto_ley": "Real Decreto-ley",
    "real_decreto": "Real Decreto",
    "decreto": "Decreto",
    "decreto_ley": "Decreto-ley",
    "decreto_legislativo": "Decreto Legislativo",
    "orden": "Orden",
    "orden_ministerial": "Orden Ministerial",
    "resolucion": "Resolución",
    "instruccion": "Instrucción",
    "circular": "Circular",
    "convenio": "Convenio",
    "acuerdo": "Acuerdo",
    "anuncio": "Anuncio",
    "correccion_errores": "Corrección de errores",
    "reglamento": "Reglamento",
    "estatuto": "Estatuto",
    "carta": "Carta",
    "tratado": "Tratado",
}

STOP_WORDS = {
    "de", "la", "el", "en", "y", "a", "que", "los", "las", "se", "del",
    "al", "por", "con", "un", "una", "para", "es", "su", "sus", "o", "e",
    "no", "si", "más", "sobre", "esta", "este", "ello", "como", "entre",
    "lo", "le", "les", "todo", "todos", "todas", "ha", "han", "hay", "ser",
    "fue", "son", "cual", "cuales",
}

# Legal abbreviations → expanded query terms for better recall
ABBREVIATIONS: dict[str, str] = {
    # Impuestos
    "irpf": "impuesto renta personas fisicas",
    "iva": "impuesto valor añadido",
    "is": "impuesto sociedades",
    "ibi": "impuesto bienes inmuebles",
    "iae": "impuesto actividades economicas",
    "isd": "impuesto sucesiones donaciones",
    "ip": "impuesto patrimonio",
    "irnr": "impuesto renta no residentes",
    "itpajd": "impuesto transmisiones patrimoniales actos juridicos documentados",
    # Leyes y códigos
    "lau": "ley arrendamientos urbanos alquiler vivienda",
    "lsc": "ley sociedades capital mercantil",
    "trlsc": "texto refundido ley sociedades capital",
    "et": "estatuto trabajadores laboral empleo",
    "lgss": "ley general seguridad social pensiones",
    "lgt": "ley general tributaria hacienda",
    "ce": "constitucion española derechos fundamentales",
    "cc": "codigo civil",
    "cp": "codigo penal delito",
    "lec": "ley enjuiciamiento civil proceso judicial",
    "lecrim": "ley enjuiciamiento criminal penal",
    "lgp": "ley general presupuestos generales estado",
    "lpac": "ley procedimiento administrativo comun administracion publica",
    "lrjsp": "regimen juridico sector publico administracion",
    "lopd": "ley proteccion datos personales privacidad",
    "rgpd": "reglamento general proteccion datos personales privacidad",
    "lopdgdd": "proteccion datos garantia derechos digitales",
    "loe": "ley organica educacion escolar",
    "lomce": "ley organica mejora calidad educativa",
    "lomloe": "ley organica modificacion educacion",
    # Prestaciones / situaciones
    "erte": "expediente regulacion temporal empleo",
    "ere": "expediente regulacion empleo",
    "imv": "ingreso minimo vital renta",
    "smi": "salario minimo interprofesional",
    "pie": "participacion ingresos estado financiacion",
    "dana": "depresion aislada niveles altos catastrofe inundacion emergencia",
    # Organismos
    "aeat": "agencia tributaria hacienda",
    "boe": "boletin oficial estado",
    "tc": "tribunal constitucional",
    "ts": "tribunal supremo",
    "tjue": "tribunal justicia union europea",
    "cedh": "convenio europeo derechos humanos",
    "ss": "seguridad social",
    "sepe": "servicio empleo publico estatal",
}

# ---------------------------------------------------------------------------
# Estado global del índice
# ---------------------------------------------------------------------------

_index: List[dict] = []
_index_ready = threading.Event()
_index_error: str | None = None
_index_total = 0
_index_loaded = 0


# ---------------------------------------------------------------------------
# Parseo de documentos
# ---------------------------------------------------------------------------

def _parse_doc(filepath: Path) -> dict | None:
    try:
        text = filepath.read_text(errors="ignore")
    except OSError:
        return None

    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    yaml_text = text[3:end].strip()
    content = text[end + 3:].strip()

    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None

    if not isinstance(meta, dict):
        return None

    # Strip markdown from content preview
    clean = re.sub(r"#+\s*", "", content)
    clean = re.sub(r"\*+", "", clean)
    clean = re.sub(r"\n{2,}", "\n", clean).strip()

    meta["_preview"] = clean[:PREVIEW_CHARS]
    meta["_region"] = filepath.parent.name
    meta["_filepath"] = str(filepath)
    meta["_filename"] = filepath.name

    # Normalise subjects to list
    subjects = meta.get("subjects")
    if isinstance(subjects, str):
        meta["subjects"] = [s.strip() for s in subjects.split(",")]
    elif not isinstance(subjects, list):
        meta["subjects"] = []

    return meta


def _build_index() -> None:
    global _index, _index_error, _index_total, _index_loaded

    # Try cache first (only valid if repo hasn't changed)
    if INDEX_CACHE.exists():
        try:
            data = json.loads(INDEX_CACHE.read_text())
            if isinstance(data, list) and len(data) > 100:
                _index = data
                _index_ready.set()
                return
        except Exception:
            pass

    docs = []
    dirs = sorted(
        [d for d in REPO_PATH.iterdir() if d.is_dir() and d.name.startswith("es")],
        key=lambda d: (0 if d.name == "es" else 1, d.name),
    )

    all_files: List[Path] = []
    for d in dirs:
        all_files.extend(sorted(d.glob("*.md")))

    _index_total = len(all_files)

    for i, fp in enumerate(all_files):
        doc = _parse_doc(fp)
        if doc:
            docs.append(doc)
        _index_loaded = i + 1

    _index = docs

    try:
        INDEX_CACHE.write_text(json.dumps(docs, ensure_ascii=False))
    except Exception:
        pass

    _index_ready.set()


threading.Thread(target=_build_index, daemon=True, name="index-builder").start()


# ---------------------------------------------------------------------------
# Motor de búsqueda
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> List[str]:
    tokens = re.findall(r"[a-záéíóúüñ]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def _expand_query(query: str) -> str:
    """Replace known abbreviations/acronyms with their full terms."""
    words = query.lower().split()
    expanded: List[str] = []
    for word in words:
        key = re.sub(r"[^a-záéíóúüñ]", "", word)
        if key in ABBREVIATIONS:
            expanded.append(ABBREVIATIONS[key])
        else:
            expanded.append(word)
    return " ".join(expanded)


def _score_doc(doc: dict, terms: List[str]) -> int:
    title = (doc.get("title") or "").lower()
    subjects = " ".join(doc.get("subjects") or []).lower()
    preview = (doc.get("_preview") or "").lower()
    dept = (doc.get("department") or "").lower()
    rank = (doc.get("rank") or "").lower()
    alerts = (doc.get("alerts") or "").lower()

    score = 0
    for term in terms:
        if term in title:
            score += 12
        if term in subjects:
            score += 8
        if term in dept:
            score += 5
        if term in alerts:
            score += 4
        if term in rank:
            score += 3
        if term in preview:
            score += 2
    return score


def search(
    query: str,
    region: str | None = None,
    rank_filter: str | None = None,
    status_filter: str | None = None,
    limit: int = MAX_RESULTS,
) -> List[dict]:
    terms = _tokenise(_expand_query(query))
    if not terms:
        return []

    results: List[tuple[int, dict]] = []

    for doc in _index:
        if region and doc.get("_region") != region:
            continue
        if rank_filter and doc.get("rank") != rank_filter:
            continue
        if status_filter and doc.get("status") != status_filter:
            continue

        score = _score_doc(doc, terms)
        if score > 0:
            results.append((score, doc))

    results.sort(key=lambda x: (x[0], x[1].get("publication_date") or ""), reverse=True)
    return [doc for _, doc in results[:limit]]


# ---------------------------------------------------------------------------
# Búsqueda semántica (HuggingFace Embeddings)
# ---------------------------------------------------------------------------

def _cosine_sim(a: list, b: list) -> float:
    try:
        import numpy as np
        va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
        d = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / d) if d > 1e-8 else 0.0
    except ImportError:
        dot  = sum(x * y for x, y in zip(a, b))
        na   = sum(x * x for x in a) ** 0.5
        nb   = sum(x * x for x in b) ** 0.5
        return dot / (na * nb) if na * nb > 1e-8 else 0.0


async def semantic_rerank(query: str, candidates: List[dict]) -> List[dict]:
    """Re-ordena candidatos por similitud semántica usando embeddings de HuggingFace."""
    if not candidates or not llm.HF_TOKEN:
        return candidates

    doc_texts = [
        f"{d.get('title', '')} | {' '.join((d.get('subjects') or [])[:6])}"
        for d in candidates
    ]
    all_texts = [query] + doc_texts

    loop = asyncio.get_event_loop()
    all_embs = await loop.run_in_executor(None, llm.embed_texts, all_texts)
    if not all_embs:
        return candidates

    query_emb = all_embs[0]
    scored = [(  _cosine_sim(query_emb, emb), doc)
              for emb, doc in zip(all_embs[1:], candidates)]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored]


# ---------------------------------------------------------------------------
# Consulta con el proveedor de IA activo
# ---------------------------------------------------------------------------

async def ask_claude(question: str, docs: List[dict]) -> str | None:
    if not llm.available():
        return None

    context_parts: List[str] = []
    for i, doc in enumerate(docs[:6], 1):
        subjects = ", ".join(doc.get("subjects") or [])
        context_parts.append(
            f"[{i}] {doc.get('title', 'Sin título')}\n"
            f"    ID: {doc.get('identifier', '')}\n"
            f"    Tipo: {RANK_LABELS.get(doc.get('rank', ''), doc.get('rank', ''))}\n"
            f"    Fecha: {doc.get('publication_date', '')}\n"
            f"    Estado: {'Vigente' if doc.get('status') == 'in_force' else doc.get('status', '')}\n"
            f"    Departamento: {doc.get('department', '')}\n"
            f"    Materias: {subjects}\n"
            f"    Fuente: {doc.get('source', '')}\n\n"
            f"    {doc.get('_preview', '')}\n"
        )

    context = "\n---\n".join(context_parts)

    system_prompt = (
        "Eres un asistente jurídico especializado en legislación española. "
        "Tu misión es ayudar a ciudadanos, empresas y profesionales a entender "
        "la normativa vigente de forma clara y práctica. "
        "Responde siempre en español. Cita los identificadores BOE cuando los menciones. "
        "Si la información no está en los documentos proporcionados, indícalo. "
        "Sé conciso pero completo. Usa listas cuando sea útil."
    )

    user_message = (
        f"Pregunta: {question}\n\n"
        f"Documentos legislativos relevantes encontrados en la base de datos:\n\n"
        f"{context}\n\n"
        "Por favor responde la pregunta basándote en estos documentos. "
        "Indica al final las referencias BOE utilizadas."
    )

    return llm.complete(system_prompt, user_message, max_tokens=1500)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Consultor Legislativo España", version="1.0.0")

app.mount("/static", StaticFiles(directory=str(REPO_PATH / "static")), name="static")


class QueryRequest(BaseModel):
    question: str
    region:   Optional[str] = None
    rank:     Optional[str] = None
    status:   Optional[str] = None
    semantic: bool = False


class DocRequest(BaseModel):
    doc_type: str
    datos: dict
    use_ai: bool = True
    context_query: Optional[str] = None


@app.get("/", response_class=FileResponse)
def root():
    return FileResponse(str(REPO_PATH / "static" / "index.html"))


@app.get("/api/status")
def api_status():
    ready = _index_ready.is_set()
    prov  = llm.provider()
    return {
        "ready":        ready,
        "total_docs":   len(_index) if ready else _index_loaded,
        "total_files":  _index_total,
        "has_ai":       llm.available(),
        "ai_provider":  prov,
        "ai_model":     llm.active_model(),
        "has_semantic": bool(llm.HF_TOKEN),
        "embed_model":  llm.HF_EMBED_MODEL if llm.HF_TOKEN else "",
        "regions":      REGIONS,
        "ranks":        RANK_LABELS,
    }


@app.get("/api/search")
async def api_search(
    q:        str           = Query(..., min_length=2),
    region:   Optional[str] = None,
    rank:     Optional[str] = None,
    status:   Optional[str] = None,
    limit:    int           = Query(default=20, le=50),
    semantic: bool          = False,
):
    if not _index_ready.is_set():
        raise HTTPException(503, "Índice en construcción, espera unos segundos.")

    pool = SEMANTIC_POOL if (semantic and llm.HF_TOKEN) else limit
    docs = search(q, region=region, rank_filter=rank, status_filter=status, limit=pool)

    if semantic and llm.HF_TOKEN and docs:
        docs = await semantic_rerank(q, docs)
        docs = docs[:limit]

    return {
        "query":    q,
        "total":    len(docs),
        "semantic": semantic and bool(llm.HF_TOKEN),
        "results":  [_serialise(d) for d in docs],
    }


@app.post("/api/ask")
async def api_ask(req: QueryRequest):
    if not _index_ready.is_set():
        raise HTTPException(503, "Índice en construcción, espera unos segundos.")

    pool = SEMANTIC_POOL if llm.HF_TOKEN else 10
    docs = search(req.question, region=req.region,
                  rank_filter=req.rank, status_filter=req.status, limit=pool)

    if llm.HF_TOKEN and docs:
        docs = await semantic_rerank(req.question, docs)

    ai_answer = await ask_claude(req.question, docs[:8])

    return {
        "question":    req.question,
        "ai_answer":   ai_answer,
        "ai_provider": llm.provider(),
        "ai_model":    llm.active_model(),
        "semantic":    bool(llm.HF_TOKEN),
        "sources":     [_serialise(d) for d in docs[:8]],
    }


@app.get("/api/recent")
def api_recent(region: Optional[str] = None, limit: int = 15):
    if not _index_ready.is_set():
        raise HTTPException(status_code=503, detail="Índice en construcción.")

    docs = [
        d for d in _index
        if (not region or d.get("_region") == region)
        and d.get("publication_date")
    ]
    docs.sort(key=lambda d: d.get("publication_date") or "", reverse=True)
    return {"results": [_serialise(d) for d in docs[:limit]]}


@app.get("/api/doc/{identifier}")
def api_doc(identifier: str):
    if not _index_ready.is_set():
        raise HTTPException(status_code=503, detail="Índice en construcción.")

    for doc in _index:
        if doc.get("identifier") == identifier or doc.get("_filename") == f"{identifier}.md":
            fp = Path(doc["_filepath"])
            try:
                full_text = fp.read_text(errors="ignore")
                end = full_text.find("---", 3)
                content = full_text[end + 3:].strip() if end != -1 else full_text
                return {**_serialise(doc), "full_content": content[:8000]}
            except OSError:
                return _serialise(doc)

    raise HTTPException(status_code=404, detail="Documento no encontrado.")


# ---------------------------------------------------------------------------
# Generación de documentos
# ---------------------------------------------------------------------------

@app.get("/api/doc-types")
def api_doc_types():
    """Catálogo de tipos de documento generables y sus campos."""
    return {
        "has_pdf": documents.LATEX_ENGINE is not None,
        "has_ai": llm.available(),
        "types": documents.doc_types_catalog(),
    }


@app.post("/api/generar")
async def api_generar(req: DocRequest):
    if req.doc_type not in documents.DOC_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de documento no válido.")

    cfg = documents.DOC_TYPES[req.doc_type]
    faltan = [
        f["label"] for f in cfg["fields"]
        if f.get("required") and not str(req.datos.get(f["name"], "")).strip()
    ]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail="Faltan campos obligatorios: " + ", ".join(faltan),
        )

    # Buscamos la normativa relacionada con el asunto/hechos para (a) dar contexto
    # a la IA y (b) citarla SIEMPRE en el documento como "Normativa aplicable",
    # aunque la IA deje vacíos los fundamentos o esté desactivada.
    query = req.context_query or req.datos.get("asunto") or req.datos.get("hechos", "")
    normativa = search(query, limit=8) if _index_ready.is_set() and query else []

    ai_sections = None
    if req.use_ai and llm.available():
        ai_sections = await documents.draft_with_claude(req.doc_type, req.datos, normativa)

    result = documents.generate(req.doc_type, req.datos, ai_sections, normativa)
    return result


@app.get("/api/generar/{doc_id}.{fmt}")
def api_download(doc_id: str, fmt: str):
    if fmt not in ("tex", "pdf"):
        raise HTTPException(status_code=400, detail="Formato no válido.")
    path = documents.file_path(doc_id, fmt)
    if not path:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    media = "application/pdf" if fmt == "pdf" else "application/x-tex"
    return FileResponse(
        str(path),
        media_type=media,
        filename=f"documento.{fmt}",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialise(doc: dict) -> dict:
    """Return a JSON-safe subset of a document record."""
    return {
        "identifier": doc.get("identifier", ""),
        "title": doc.get("title", "Sin título"),
        "rank": doc.get("rank", ""),
        "rank_label": RANK_LABELS.get(doc.get("rank", ""), doc.get("rank", "")),
        "publication_date": doc.get("publication_date", ""),
        "last_updated": doc.get("last_updated", ""),
        "status": doc.get("status", ""),
        "department": doc.get("department", ""),
        "subjects": doc.get("subjects") or [],
        "source": doc.get("source", ""),
        "pdf_url": doc.get("pdf_url") or doc.get("url_pdf", ""),
        "scope": doc.get("scope", ""),
        "region": REGIONS.get(doc.get("_region", ""), doc.get("_region", "")),
        "region_code": doc.get("_region", ""),
        "preview": doc.get("_preview", ""),
        "official_number": doc.get("official_number", ""),
        "alerts": doc.get("alerts", ""),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
