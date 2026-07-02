"""
Capa de abstracción del proveedor de IA.

Cadena de prioridad (el primero disponible gana):
  1. LLM LOCAL  – llama.cpp en GPU (gratis, privado, sin latencia de red)
  2. HUGGINGFACE – Inference API en la nube (gratuito con HF_TOKEN)
  3. ANTHROPIC   – Claude API (calidad máxima con ANTHROPIC_API_KEY)

Variables de entorno:
    LOCAL_LLM_URL     (por defecto http://127.0.0.1:8080/v1)
    LOCAL_LLM_MODEL   (por defecto "local"; llama.cpp ignora el nombre)
    HF_TOKEN          → activa HuggingFace como fallback
    HF_MODEL          → modelo HF de generación (por defecto Mistral-7B-Instruct)
    HF_EMBED_MODEL    → modelo de embeddings para búsqueda semántica
    ANTHROPIC_API_KEY → activa Anthropic como fallback
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

LOCAL_LLM_URL  = os.environ.get("LOCAL_LLM_URL",    "http://127.0.0.1:8080/v1").rstrip("/")
LOCAL_LLM_MODEL = os.environ.get("LOCAL_LLM_MODEL",  "local")
HF_TOKEN        = os.environ.get("HF_TOKEN",          "")
HF_GEN_MODEL    = os.environ.get("HF_MODEL",         "mistralai/Mistral-7B-Instruct-v0.2")
HF_EMBED_MODEL  = os.environ.get("HF_EMBED_MODEL",
                                  "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")


# ---------------------------------------------------------------------------
# Detección de proveedores
# ---------------------------------------------------------------------------

def _local_reachable() -> bool:
    """Prueba si el servidor llama.cpp responde (sin enviar una petición real)."""
    try:
        req = urllib.request.Request(
            f"{LOCAL_LLM_URL}/models",
            headers={"Accept": "application/json"},
            method="GET",
        )
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def provider() -> str:
    """Devuelve el proveedor activo: 'local', 'huggingface', 'anthropic' o 'none'."""
    if _local_reachable():
        return "local"
    if HF_TOKEN:
        return "huggingface"
    if ANTHROPIC_KEY:
        return "anthropic"
    return "none"


def available() -> bool:
    """¿Hay algún backend de IA disponible?"""
    if _local_reachable():
        return True
    return bool(HF_TOKEN or ANTHROPIC_KEY)


def active_model() -> str:
    """Nombre del modelo que se usará en la próxima llamada."""
    p = provider()
    if p == "local":
        return LOCAL_LLM_MODEL
    if p == "huggingface":
        return HF_GEN_MODEL
    if p == "anthropic":
        return "claude-opus-4-8"
    return ""


# ---------------------------------------------------------------------------
# Backend local (llama.cpp OpenAI-compatible)
# ---------------------------------------------------------------------------

def _complete_local(system: str, user: str, max_tokens: int) -> Optional[str]:
    payload = json.dumps({
        "model": LOCAL_LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(3):
        req = urllib.request.Request(
            f"{LOCAL_LLM_URL}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code >= 500 and attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue
            return f"⚠️ El modelo local respondió con error HTTP {exc.code}: {exc}"
        except urllib.error.URLError as exc:
            return (f"⚠️ No se pudo conectar con el modelo local ({LOCAL_LLM_URL}). "
                    f"¿Está arrancado llama-server? Detalle: {exc}")
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            return f"⚠️ Respuesta inesperada del modelo local: {exc}"

    return f"⚠️ El modelo local falló tras varios intentos: {last_exc}"


# ---------------------------------------------------------------------------
# Backend HuggingFace Inference API
# ---------------------------------------------------------------------------

def _complete_hf(system: str, user: str, max_tokens: int) -> Optional[str]:
    try:
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=HF_TOKEN)
        resp = client.chat_completion(
            model    = HF_GEN_MODEL,
            messages = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens  = max_tokens,
            temperature = 0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        return f"⚠️ Error con HuggingFace ({HF_GEN_MODEL}): {exc}"


# ---------------------------------------------------------------------------
# Backend Anthropic Claude
# ---------------------------------------------------------------------------

def _complete_anthropic(system: str, user: str, max_tokens: int) -> Optional[str]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model      = "claude-opus-4-8",
            max_tokens = max_tokens,
            system     = system,
            messages   = [{"role": "user", "content": user}],
        )
        return msg.content[0].text
    except Exception as exc:
        return f"⚠️ Error con Anthropic Claude: {exc}"


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def complete(system: str, user: str, max_tokens: int = 1500) -> Optional[str]:
    """Genera una respuesta usando el mejor proveedor disponible en este momento."""
    p = provider()
    if p == "local":
        return _complete_local(system, user, max_tokens)
    if p == "huggingface":
        return _complete_hf(system, user, max_tokens)
    if p == "anthropic":
        return _complete_anthropic(system, user, max_tokens)
    return None


# ---------------------------------------------------------------------------
# Embeddings para búsqueda semántica (siempre via HuggingFace)
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Genera embeddings para una lista de textos usando HF Inference API.

    Devuelve None si HF_TOKEN no está configurado o la llamada falla.
    """
    if not HF_TOKEN:
        return None
    try:
        import numpy as np
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=HF_TOKEN)

        all_embs: list[list[float]] = []
        for i in range(0, len(texts), 24):
            batch  = texts[i : i + 24]
            result = client.feature_extraction(batch, model=HF_EMBED_MODEL)
            arr    = np.array(result, dtype=float)
            if arr.ndim == 3:
                arr = arr.mean(axis=1)
            elif arr.ndim == 1:
                arr = arr.reshape(1, -1)
            all_embs.extend(arr.tolist())
        return all_embs

    except Exception as exc:
        print(f"[llm.embed_texts] error: {exc}")
        return None
