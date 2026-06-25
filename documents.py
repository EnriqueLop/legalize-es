"""
Generación de documentos administrativos (LaTeX → PDF).

Define un catálogo de tipos de documento (hoja de queja, solicitud genérica,
recurso de alzada…), rellena una plantilla LaTeX controlada con los datos del
interesado y, opcionalmente, con una redacción jurídica generada por Claude que
cita la normativa BOE relevante. El .tex resultante se compila con `pdflatex`.

El diseño separa "plantilla controlada" de "contenido generado": la estructura
LaTeX la fijamos nosotros (para que compile siempre) y la IA sólo aporta texto
que insertamos escapado. Así una respuesta inesperada del modelo no rompe la
compilación.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

# Carpeta donde se guardan los documentos generados (.tex y .pdf).
DOCS_DIR = Path(tempfile.gettempdir()) / "legalize_docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# XeLaTeX es el compilador recomendado: maneja UTF-8 y fuentes del sistema de
# forma nativa y funciona con polyglossia. Si no estuviera, caemos a pdflatex.
XELATEX = shutil.which("xelatex")
PDFLATEX = shutil.which("pdflatex")
LATEX_ENGINE = XELATEX or PDFLATEX

# ---------------------------------------------------------------------------
# Catálogo de tipos de documento
# ---------------------------------------------------------------------------
# Cada tipo define las etiquetas de sus secciones y los campos del formulario.
# `fields` se usa tanto para construir el formulario en el frontend como para
# validar lo que llega al backend.

COMMON_FIELDS = [
    {"name": "nombre", "label": "Nombre y apellidos", "required": True},
    {"name": "dni", "label": "DNI / NIE", "required": True},
    {"name": "domicilio", "label": "Domicilio a efectos de notificación", "required": False},
    {"name": "email", "label": "Correo electrónico", "required": False},
    {"name": "telefono", "label": "Teléfono", "required": False},
    {"name": "organismo", "label": "Órgano / organismo destinatario", "required": True},
    {"name": "lugar", "label": "Lugar (ciudad)", "required": False},
    {"name": "asunto", "label": "Asunto", "required": False},
    {"name": "hechos", "label": "Hechos / motivo (descríbelo con tus palabras)", "required": True,
     "multiline": True},
    {"name": "peticion", "label": "Qué solicitas", "required": True, "multiline": True},
]

DOC_TYPES: dict[str, dict] = {
    "solicitud": {
        "label": "Solicitud / Instancia genérica",
        "description": "Escrito dirigido a una Administración para pedir algo "
                       "(autorización, prestación, certificado, etc.).",
        "titulo": "SOLICITUD",
        "verbo_expone": "EXPONE",
        "verbo_solicita": "SOLICITA",
        "fields": COMMON_FIELDS,
    },
    "hoja_queja": {
        "label": "Hoja de queja / reclamación",
        "description": "Reclamación formal por un servicio, actuación o trato "
                       "recibido de una Administración o entidad.",
        "titulo": "HOJA DE QUEJA / RECLAMACIÓN",
        "verbo_expone": "EXPONE LOS SIGUIENTES HECHOS",
        "verbo_solicita": "RECLAMA",
        "fields": COMMON_FIELDS,
    },
    "recurso_alzada": {
        "label": "Recurso de alzada",
        "description": "Recurso administrativo contra una resolución, ante el "
                       "órgano superior jerárquico (art. 121-122 Ley 39/2015).",
        "titulo": "RECURSO DE ALZADA",
        "verbo_expone": "ALEGA",
        "verbo_solicita": "SUPLICA",
        "fields": COMMON_FIELDS + [
            {"name": "acto_recurrido", "label": "Resolución / acto que se recurre",
             "required": True},
            {"name": "fecha_acto", "label": "Fecha de la resolución recurrida",
             "required": False},
            {"name": "organo_autor", "label": "Órgano que dictó la resolución",
             "required": False},
        ],
    },
}


def doc_types_catalog() -> List[dict]:
    """Catálogo serializable para el frontend."""
    return [
        {
            "id": key,
            "label": cfg["label"],
            "description": cfg["description"],
            "fields": cfg["fields"],
        }
        for key, cfg in DOC_TYPES.items()
    ]


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

_LATEX_REPLACEMENTS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    """Escapa los caracteres especiales de LaTeX en texto de usuario."""
    if not text:
        return ""
    out = []
    for ch in str(text):
        out.append(_LATEX_REPLACEMENTS.get(ch, ch))
    return "".join(out)


def _paragraphs(text: str) -> str:
    """Convierte saltos de línea dobles en párrafos LaTeX, escapando todo."""
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text.strip())
    return "\n\n".join(latex_escape(b.strip()) for b in blocks if b.strip())


def _normativa_block(normativa: Optional[List[dict]]) -> str:
    """Lista de normativa real encontrada en el índice, citada con su BOE.

    Se incluye siempre que haya resultados, con independencia de lo que redacte
    la IA: garantiza que el documento referencie legislación existente (no
    inventada) relacionada con la materia.
    """
    if not normativa:
        return ""
    items: List[str] = []
    for doc in normativa[:6]:
        ident = (doc.get("identifier") or "").strip()
        if not ident:
            continue
        title = (doc.get("title") or "Sin título").strip()
        date = (doc.get("publication_date") or "").strip()
        meta = ", ".join(filter(None, [ident, date]))
        ref = f"{title} ({meta})" if meta else title
        items.append("\\item " + latex_escape(ref))
    if not items:
        return ""
    return (
        "\\section*{NORMATIVA APLICABLE}\n"
        "\\noindent A los efectos del presente escrito se considera de aplicación, "
        "entre otra, la siguiente normativa publicada en el BOE:\n"
        "\\begin{itemize}\n" + "\n".join(items) + "\n\\end{itemize}\n"
    )


def build_latex(
    doc_type: str,
    datos: dict,
    ai_sections: Optional[dict] = None,
    normativa: Optional[List[dict]] = None,
) -> str:
    """Construye el documento LaTeX completo.

    `ai_sections` (opcional) puede traer claves `exposicion`, `fundamentos` y
    `solicitud` redactadas por la IA. Si no, se usa el texto literal del usuario.
    `normativa` (opcional) es la lista de normas encontradas en el índice, que se
    citan en una sección "Normativa aplicable".
    """
    cfg = DOC_TYPES[doc_type]
    e = latex_escape  # alias corto

    nombre = e(datos.get("nombre", ""))
    dni = e(datos.get("dni", ""))
    domicilio = e(datos.get("domicilio", ""))
    email = e(datos.get("email", ""))
    telefono = e(datos.get("telefono", ""))
    organismo = e(datos.get("organismo", ""))
    lugar = e(datos.get("lugar", "")) or "________________"
    asunto = e(datos.get("asunto", ""))

    ai = ai_sections or {}
    exposicion = _paragraphs(ai.get("exposicion") or datos.get("hechos", ""))
    solicitud = _paragraphs(ai.get("solicitud") or datos.get("peticion", ""))
    fundamentos = _paragraphs(ai.get("fundamentos") or "")

    # Datos identificativos del interesado
    ident_lines = [f"\\textbf{{{nombre}}}, con DNI/NIE \\textbf{{{dni}}}"]
    if domicilio:
        ident_lines.append(f"y domicilio a efectos de notificaciones en {domicilio}")
    contacto = ", ".join(filter(None, [
        f"correo electrónico {email}" if email else "",
        f"teléfono {telefono}" if telefono else "",
    ]))
    ident = " ".join(ident_lines) + ("" if not contacto else f" ({contacto})")

    # Bloque específico del recurso de alzada
    extra = ""
    if doc_type == "recurso_alzada":
        acto = e(datos.get("acto_recurrido", ""))
        fecha_acto = e(datos.get("fecha_acto", ""))
        organo_autor = e(datos.get("organo_autor", ""))
        det = acto
        if fecha_acto:
            det += f", de fecha {fecha_acto}"
        if organo_autor:
            det += f", dictada por {organo_autor}"
        extra = (
            "\\medskip\n\\noindent Que, mediante el presente escrito, interpongo "
            "\\textbf{RECURSO DE ALZADA} contra la resolución siguiente: "
            f"{det}.\n"
        )

    fundamentos_block = ""
    if fundamentos:
        fundamentos_block = (
            "\\section*{FUNDAMENTOS DE DERECHO}\n" + fundamentos + "\n"
        )

    normativa_block = _normativa_block(normativa)

    asunto_block = f"\\noindent\\textbf{{Asunto:}} {asunto}\\par\\medskip\n" if asunto else ""

    # XeLaTeX (recomendado) usa fontspec + polyglossia; UTF-8 y fuentes nativas.
    # Fallback a pdflatex con babel para instalaciones sin XeLaTeX.
    if XELATEX:
        lang_preamble = (
            "\\usepackage{fontspec}\n"
            "\\usepackage{polyglossia}\n"
            "\\setdefaultlanguage{spanish}\n"
        )
    else:
        lang_preamble = (
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage[T1]{fontenc}\n"
            "\\usepackage[spanish,provide=*]{babel}\n"
            "\\usepackage{lmodern}\n"
        )

    tex = rf"""\documentclass[11pt,a4paper]{{article}}
{lang_preamble}\usepackage[margin=2.5cm]{{geometry}}
\usepackage{{parskip}}
\setlength{{\parindent}}{{0pt}}

\begin{{document}}

\begin{{center}}
{{\large\bfseries {e(cfg["titulo"])}}}
\end{{center}}

\bigskip

{asunto_block}\noindent\textbf{{DESTINATARIO:}} {organismo}\par
\medskip

\noindent\textbf{{DATOS DEL INTERESADO/A:}}\par
\noindent {ident}.\par
\bigskip

{extra}
\section*{{{e(cfg["verbo_expone"])}}}
{exposicion}

{fundamentos_block}{normativa_block}
\section*{{{e(cfg["verbo_solicita"])}}}
{solicitud}

\bigskip
\noindent En {lugar}, a \rule{{3cm}}{{0.4pt}} de \rule{{3cm}}{{0.4pt}} de 20\rule{{0.8cm}}{{0.4pt}}.

\bigskip\bigskip
\noindent Fdo.: {nombre}

\vfill
\noindent\footnotesize\textit{{Documento generado automáticamente por el Consultor
Legislativo. No constituye asesoramiento jurídico profesional; revise los datos y
la normativa citada antes de presentarlo.}}

\end{{document}}
"""
    return tex


def compile_pdf(tex: str, workdir: Path) -> Optional[Path]:
    """Compila el .tex a PDF con XeLaTeX (o pdflatex). Devuelve la ruta o None."""
    if not LATEX_ENGINE:
        return None

    tex_path = workdir / "documento.tex"
    tex_path.write_text(tex, encoding="utf-8")

    try:
        subprocess.run(
            [LATEX_ENGINE, "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", str(workdir), str(tex_path)],
            capture_output=True,
            timeout=60,
            cwd=str(workdir),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    pdf_path = workdir / "documento.pdf"
    return pdf_path if pdf_path.exists() else None


# ---------------------------------------------------------------------------
# Redacción asistida por Claude
# ---------------------------------------------------------------------------

async def draft_with_claude(doc_type: str, datos: dict, normativa: List[dict]) -> Optional[dict]:
    """Pide al modelo local una redacción formal estructurada (JSON).

    Devuelve un dict con claves `exposicion`, `fundamentos`, `solicitud`, o None
    si no hay backend de IA o falla la llamada.
    """
    import llm

    if not llm.available():
        return None

    cfg = DOC_TYPES[doc_type]

    ctx_parts: List[str] = []
    for i, doc in enumerate(normativa[:6], 1):
        ctx_parts.append(
            f"[{i}] {doc.get('title', 'Sin título')} "
            f"(BOE {doc.get('identifier', '')}, {doc.get('publication_date', '')})"
        )
    contexto = "\n".join(ctx_parts) or "No se han encontrado normas específicas."

    system_prompt = (
        "Eres un jurista que redacta escritos administrativos en español, en "
        "estilo formal y respetuoso. Redactas en primera persona del interesado. "
        "Tu objetivo es dar el MÁXIMO peso jurídico a la solicitud, apoyándola en "
        "la normativa aportada. Cita ÚNICAMENTE identificadores BOE que aparezcan "
        "en la lista de normativa proporcionada; no inventes normas, artículos ni "
        "referencias que no estén en esa lista. Devuelve EXCLUSIVAMENTE un objeto "
        "JSON válido con las claves: exposicion, fundamentos, solicitud. Sin texto "
        "adicional ni markdown."
    )

    user_message = (
        f"Tipo de documento: {cfg['label']}\n"
        f"Datos aportados por el ciudadano:\n{json.dumps(datos, ensure_ascii=False, indent=2)}\n\n"
        f"Normativa aplicable encontrada en la base de datos (cita SÓLO de aquí):\n{contexto}\n\n"
        "Redacta:\n"
        "- exposicion: los hechos/motivos de forma ordenada y formal.\n"
        "- fundamentos: fundamentos jurídicos que refuercen la solicitud, citando "
        "los identificadores BOE de la lista anterior que sean pertinentes. Sólo si "
        "ninguna norma de la lista guarda relación con el asunto, deja una cadena vacía.\n"
        "- solicitud: lo que se pide, de forma concreta y firme.\n"
        "Responde sólo con el JSON."
    )

    raw = llm.complete(system_prompt, user_message, max_tokens=1500)
    if not raw:
        return None

    # Extraer el primer bloque JSON aunque venga con texto alrededor.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "exposicion": str(data.get("exposicion", "")),
        "fundamentos": str(data.get("fundamentos", "")),
        "solicitud": str(data.get("solicitud", "")),
    }


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def generate(
    doc_type: str,
    datos: dict,
    ai_sections: Optional[dict],
    normativa: Optional[List[dict]] = None,
) -> dict:
    """Construye el .tex, lo compila y lo guarda. Devuelve metadatos + token."""
    doc_id = uuid.uuid4().hex[:16]
    workdir = DOCS_DIR / doc_id
    workdir.mkdir(parents=True, exist_ok=True)

    tex = build_latex(doc_type, datos, ai_sections, normativa)
    (workdir / "documento.tex").write_text(tex, encoding="utf-8")

    pdf_path = compile_pdf(tex, workdir)

    citada = [
        {"identifier": d.get("identifier", ""), "title": d.get("title", "")}
        for d in (normativa or [])[:6]
        if d.get("identifier")
    ]

    return {
        "doc_id": doc_id,
        "latex": tex,
        "pdf_available": pdf_path is not None,
        "used_ai": ai_sections is not None,
        "normativa": citada,
    }


def file_path(doc_id: str, fmt: str) -> Optional[Path]:
    """Ruta de un fichero generado (validando el doc_id contra path traversal)."""
    if not re.fullmatch(r"[0-9a-f]{16}", doc_id):
        return None
    name = "documento.tex" if fmt == "tex" else "documento.pdf"
    path = DOCS_DIR / doc_id / name
    return path if path.exists() else None
