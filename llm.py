"""
Capa de abstracción del proveedor de IA.

Utiliza un modelo local servido por llama.cpp (gratis, en la GPU, datos privados).

Variables para el modo local:
    LOCAL_LLM_URL    (por defecto http://127.0.0.1:8080/v1)
    LOCAL_LLM_MODEL  (por defecto "local"; llama.cpp ignora el nombre)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional


def available() -> bool:
    """¿Hay un backend de IA utilizable según la configuración actual?"""
    return True


def complete(system: str, user: str, max_tokens: int = 1500) -> Optional[str]:
    """Devuelve la respuesta del modelo como texto, o None si falla/indisponible."""
    base = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1").rstrip("/")
    model = os.environ.get("LOCAL_LLM_MODEL", "local")
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")

    # Reintentamos ante errores 5xx transitorios del servidor (p. ej. el modelo
    # devuelve una respuesta que el parser interno no digiere); el reintento
    # vuelve a muestrear y suele salir limpio.
    last_exc: Exception | None = None
    for attempt in range(3):
        req = urllib.request.Request(
            f"{base}/chat/completions",
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
            return f"⚠️ El modelo local respondió con un error ({exc.code}): {exc}"
        except urllib.error.URLError as exc:
            return ("⚠️ No se pudo conectar con el modelo local. ¿Está arrancado "
                    f"llama-server en {base}? Detalle: {exc}")
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            return f"⚠️ Respuesta inesperada del modelo local: {exc}"

    return f"⚠️ El modelo local falló tras varios intentos: {last_exc}"
