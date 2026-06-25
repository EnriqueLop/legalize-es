# legalize-es

Legislación de España en formato Markdown, versionada como repositorio git.

Cada ley es un archivo; cada reforma es un commit con la fecha real de publicación oficial. El `git log` de cada ley te muestra su historia completa — cuándo se sancionó, qué artículos se modificaron y por qué norma.

Cubre legislación estatal española y normativa de las comunidades autónomas publicada en el BOE, en su versión consolidada (texto vigente con todas sus redacciones). Cada norma es un fichero Markdown y cada reforma es un commit de git con la fecha oficial de publicación. Las normas de ámbito estatal se ubican en el directorio es/ y las autonómicas en directorios por jurisdicción (es-pv/, es-ct/, etc.). Datos obtenidos de la API de datos abiertos del BOE.

---

## 🏛️ Consultor Legislativo (aplicación web)

Además del dataset, este repositorio incluye una **aplicación web** (`app.py`) que indexa toda la legislación y permite:

- **Buscar** normativa por palabras clave o acrónimos (IRPF, LAU, RGPD, ET…), con filtros por comunidad autónoma, rango y estado.
- **Preguntar a un Asistente Jurídico** que responde en lenguaje natural citando los identificadores BOE de las normas relevantes.
- **Generar borradores de documentos administrativos** (solicitud, hoja de queja, recurso de alzada) en LaTeX/PDF, redactados por la IA e incorporando automáticamente una sección de **normativa aplicable** con las leyes reales encontradas.

Toda la IA se ejecuta **en local** (modelo en la GPU vía [llama.cpp](https://github.com/ggml-org/llama.cpp)): es gratis y los datos no salen de tu equipo.

### Requisitos

- **Python 3.10+** y las dependencias de `requirements.txt` (`fastapi`, `uvicorn`, `python-multipart`, `PyYAML`).
- **Modelo local** servido por `llama-server` (llama.cpp) exponiendo una API compatible con OpenAI. El script `start-local-llm.sh` lo arranca con el modelo **Qwen2.5-7B-Instruct** en GPU (Vulkan).
- *(Opcional)* **XeLaTeX** o **pdflatex** para compilar los documentos a PDF. Sin ellos, la app sigue generando el `.tex` descargable.

### Arranque rápido

```bash
./start.sh
```

Este script instala las dependencias que falten, levanta el modelo local en `:8080` y la aplicación web en **http://localhost:8000**. La primera vez, el índice de documentos se construye en segundo plano (~60-90 s).

### Arranque manual (dos terminales)

```bash
# 1) Modelo de IA local (API OpenAI-compatible en :8080)
./start-local-llm.sh

# 2) Aplicación web (en otra terminal) -> http://localhost:8000
python3 app.py
```

### Ejemplos de uso

Desde la interfaz web (`http://localhost:8000`) o directamente contra la API:

**1. Buscar por acrónimo** — los acrónimos se expanden automáticamente:

```bash
curl "http://localhost:8000/api/search?q=IRPF%20deduccion%20vivienda&limit=5"
```

**2. Preguntar al Asistente Jurídico:**

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Cuántos días de permiso por fallecimiento de un familiar tengo según el Estatuto de los Trabajadores?"}'
```

**3. Generar un recurso de alzada con normativa aplicable:**

```bash
curl -X POST http://localhost:8000/api/generar \
  -H "Content-Type: application/json" \
  -d '{
    "doc_type": "recurso_alzada",
    "use_ai": true,
    "datos": {
      "nombre": "Ana García", "dni": "12345678Z",
      "organismo": "Ayuntamiento de Madrid",
      "hechos": "Me han denegado una licencia de obra sin motivar la resolución",
      "peticion": "Que se anule la resolución y se conceda la licencia",
      "acto_recurrido": "Resolución 2024/123"
    }
  }'
# Descarga: /api/generar/<doc_id>.tex  y  /api/generar/<doc_id>.pdf
```

Casos de uso típicos: reclamar una brecha de datos ante la AEPD, recurrir una multa, solicitar una prestación, presentar una hoja de queja por un servicio público, etc.

### Personalización

Sí, la aplicación es totalmente personalizable. Puntos principales:

| Qué cambiar | Dónde |
|---|---|
| **Modelo de IA** (otro GGUF, tamaño o cuantización) | línea `-hf …` de `start-local-llm.sh` |
| **GPU / dispositivo y contexto** | `--device`, `-ngl`, `-c` en `start-local-llm.sh` |
| **Usar otro servidor LLM** (OpenAI-compatible, remoto) | variables `LOCAL_LLM_URL` y `LOCAL_LLM_MODEL` (ver `llm.py`) |
| **Puertos** | `8000` en `app.py` (uvicorn); `8080` en `start-local-llm.sh` |
| **Tipos de documento** y sus campos | diccionario `DOC_TYPES` en `documents.py` |
| **Acrónimos jurídicos** reconocidos en la búsqueda | diccionario `ABBREVIATIONS` en `app.py` |
| **Comunidades autónomas / etiquetas de rango** | diccionarios `REGIONS` y `RANK_LABELS` en `app.py` |
| **Aspecto visual y textos** de la interfaz | `static/index.html` |

Por ejemplo, para apuntar a un servidor de IA distinto sin tocar código:

```bash
export LOCAL_LLM_URL="http://mi-servidor:8080/v1"
export LOCAL_LLM_MODEL="mi-modelo"
python3 app.py
```

> **Nota:** `start-local-llm.sh` está afinado para una GPU **Radeon RX 7600 (Vulkan)** y rutas bajo `~/llamacpp/`. Ajústalo a tu hardware (dispositivo, número de capas en GPU, ruta del binario de llama.cpp).

### Créditos

El Consultor Legislativo (aplicación web e IA local) es una contribución de [@nomada1980-IABD](https://github.com/nomada1980-IABD). Herramienta de uso público, libre y abierta, construida sobre el dataset legislativo de Legalize.

---

## Qué contiene

- **Constitución** (`BOE-A-AAAA-N.md`) — `es/BOE-A-1978-31229.md`
- **Ley orgánica** (`BOE-A-AAAA-N.md`) — Rango: ley_organica.
- **Ley** (`BOE-A-AAAA-N.md`) — `es/BOE-A-2015-11430.md`
- **Real Decreto-ley** (`BOE-A-AAAA-N.md`) — Rango: real_decreto_ley.
- **Real Decreto Legislativo** (`BOE-A-AAAA-N.md`) — `es/BOE-A-1996-8930.md`
- **Real Decreto** (`BOE-A-AAAA-N.md`) — Rango: real_decreto.
- **Otros rangos estatales** (`BOE-A-AAAA-N.md`) — Orden, Resolución, Circular, Instrucción, Acuerdo, Decreto, Acuerdo internacional.
- **Normativa autonómica (foral/regional)** (`es-XX/BOE-A-AAAA-N.md`) — Leyes y decretos de comunidades autónomas, ubicados en directorios por jurisdicción ELI (es-pv, es-ct, es-ga, etc.). Incluye rangos forales: ley foral, decreto legislativo, decreto-ley, decreto-ley foral, decreto foral legislativo.

## Fuente de los datos

- **BOE — Agencia Estatal Boletín Oficial del Estado**
  - Portal: https://www.boe.es
  - Datos abiertos (API): https://www.boe.es/datosabiertos
  - Legislación consolidada: https://www.boe.es/legislacion/legislacion_ava.php
  - Condiciones de reutilización / Aviso legal: https://www.boe.es/informacion/aviso_legal/index.php

## Atribución

> Fuente de los datos: Agencia Estatal Boletín Oficial del Estado (https://www.boe.es). Datos reutilizados conforme a las condiciones de reutilización del BOE (Resolución de 27 de junio de 2024). Este repositorio es una obra derivada basada en datos de la Agencia Estatal Boletín Oficial del Estado.

## Estructura de ficheros

Estructura plana: un directorio por ámbito (es/ para el Estado; es-XX/ por comunidad autónoma según código ELI). El rango de la norma (constitución, ley orgánica, ley, real decreto, etc.) figura en el frontmatter YAML, nunca en la ruta del fichero.

## Limitaciones

Las imágenes del texto original se omiten (el proyecto no incorpora activos binarios). Se conserva el texto, las tablas, el formato enriquecido y los metadatos. El identificador del fichero es el ID oficial del BOE; un cambio de formato implicaría regenerar todo el historial de commits.

## Otros países

Este repositorio es parte del proyecto **Legalize**, que mantiene legislación de múltiples países como repos git. Ver https://legalize.dev para el catálogo completo.

## Apoyar

Legalize es libre y abierto. Si este trabajo te resulta útil, puedes ayudar a sostener su alojamiento y desarrollo: [Apoya este proyecto](https://buymeacoffee.com/legalizedev).

## Licencia

- **Código del pipeline**: MIT (https://github.com/legalize-dev/legalize-pipeline)
- **Datos**: Condiciones de reutilización del BOE — cita obligatoria de la fuente
