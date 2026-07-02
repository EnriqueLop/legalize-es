# legalize-es

Legislación de España en formato Markdown, versionada como repositorio git.

Cada ley es un archivo; cada reforma es un commit con la fecha real de publicación oficial. El `git log` de cada ley te muestra su historia completa — cuándo se sancionó, qué artículos se modificaron y por qué norma.

Cubre legislación estatal española y normativa de las comunidades autónomas publicada en el BOE, en su versión consolidada (texto vigente con todas sus redacciones). Cada norma es un fichero Markdown y cada reforma es un commit de git con la fecha oficial de publicación. Las normas de ámbito estatal se ubican en el directorio `es/` y las autonómicas en directorios por jurisdicción (`es-pv/`, `es-ct/`, etc.). Datos obtenidos de la API de datos abiertos del BOE.

---

## 🏛️ Consultor Legislativo (aplicación web)

Además del dataset, este repositorio incluye una **aplicación web** (`app.py`) que indexa toda la legislación (~12 000 normas) y permite:

- **Buscar** normativa por palabras clave o acrónimos (IRPF, LAU, RGPD, ET, ERTE, DANA…), con filtros por comunidad autónoma, rango y estado de vigencia.
- **Búsqueda semántica** — re-ordena los resultados usando embeddings multilingües de HuggingFace para encontrar normas temáticamente relacionadas aunque no coincidan literalmente.
- **Preguntar a un Asistente Jurídico** que responde en lenguaje natural citando los identificadores BOE de las normas relevantes.
- **Generar borradores de documentos administrativos** (solicitud, hoja de queja, recurso de alzada) en LaTeX/PDF, redactados por la IA e incorporando automáticamente la normativa aplicable.

### Modos de IA — independiente de proveedor

La aplicación detecta y usa automáticamente el mejor proveedor disponible, en este orden de prioridad:

| Prioridad | Proveedor | Variable de entorno | Nota |
|-----------|-----------|---------------------|------|
| 1 | **IA local** (llama.cpp / GPU) | `LOCAL_LLM_URL` | Gratis, privado, sin latencia de red |
| 2 | **HuggingFace** (nube) | `HF_TOKEN` | Gratuito con cuenta HF; no necesita GPU |
| 3 | **Anthropic Claude** (nube) | `ANTHROPIC_API_KEY` | Máxima calidad |
| — | Sin IA | *(ninguna)* | Búsqueda por palabras clave igualmente funcional |

No es necesario configurar todos los proveedores: con solo `HF_TOKEN` la aplicación ya es completamente funcional en la nube.

---

### Inicio rápido — solo HuggingFace (sin GPU)

```bash
git clone https://github.com/nomada1980-IABD/legalize-es_fork
cd legalize-es_fork
pip install -r requirements.txt

export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx   # token gratuito en huggingface.co
python3 app.py
# → http://localhost:8000
```

La primera vez el índice se construye en segundo plano (~60-90 s). Una vez listo, el badge de estado cambia a verde y el badge de proveedor muestra "🤗 HuggingFace".

Para la búsqueda semántica, la app usará el mismo `HF_TOKEN` con el modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

---

### Inicio con IA local (GPU)

```bash
./start.sh
```

Este script instala las dependencias, levanta el modelo local (**Qwen2.5-7B-Instruct** vía llama.cpp en `:8080`) y la aplicación en **http://localhost:8000**.

Arranque manual en dos terminales:

```bash
# Terminal 1 — modelo local (API OpenAI-compatible en :8080)
./start-local-llm.sh

# Terminal 2 — aplicación web → http://localhost:8000
python3 app.py
```

---

### Variables de entorno

| Variable | Valor por defecto | Descripción |
|----------|------------------|-------------|
| `LOCAL_LLM_URL` | `http://127.0.0.1:8080/v1` | Endpoint OpenAI-compatible del modelo local |
| `LOCAL_LLM_MODEL` | `local` | Nombre de modelo enviado al servidor local |
| `HF_TOKEN` | *(vacío)* | Token de HuggingFace — activa generación y embeddings HF |
| `HF_MODEL` | `mistralai/Mistral-7B-Instruct-v0.2` | Modelo de generación HuggingFace |
| `HF_EMBED_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Modelo de embeddings para búsqueda semántica |
| `ANTHROPIC_API_KEY` | *(vacío)* | Clave Anthropic — activa Claude como fallback |

---

### Requisitos

- **Python 3.10+** y las dependencias de `requirements.txt`:
  ```
  fastapi, uvicorn, python-multipart, PyYAML, huggingface_hub, numpy, anthropic
  ```
- *(Solo para IA local)* `llama-server` (llama.cpp) con el modelo `.gguf` descargado.
- *(Opcional)* **XeLaTeX** o **pdflatex** para compilar documentos a PDF. Sin ellos, la app genera el `.tex` descargable.

---

### Ejemplos de uso — API

**1. Buscar por acrónimo** (los acrónimos se expanden automáticamente):

```bash
curl "http://localhost:8000/api/search?q=IRPF%20deduccion%20vivienda&limit=5"
```

**2. Búsqueda semántica** (re-ordenación por embeddings):

```bash
curl "http://localhost:8000/api/search?q=permiso+maternidad&semantic=true&limit=10"
```

**3. Preguntar al Asistente Jurídico:**

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"¿Cuántos días de permiso por fallecimiento de un familiar tengo según el Estatuto de los Trabajadores?","semantic":true}'
```

**4. Generar un recurso de alzada con normativa aplicable:**

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
# Descargar resultado:
# GET /api/generar/<doc_id>.tex
# GET /api/generar/<doc_id>.pdf
```

Casos de uso típicos: reclamar una brecha de datos ante la AEPD, recurrir una multa, solicitar una prestación, presentar una hoja de queja por un servicio público, etc.

---

### Personalización

| Qué cambiar | Dónde |
|---|---|
| **Proveedor de IA** activo | Variables de entorno `HF_TOKEN`, `ANTHROPIC_API_KEY`, `LOCAL_LLM_URL` |
| **Modelo de generación HF** | Variable `HF_MODEL` |
| **Modelo de embeddings HF** | Variable `HF_EMBED_MODEL` |
| **Modelo local** (otro GGUF, cuantización) | línea `-hf …` de `start-local-llm.sh` |
| **GPU / dispositivo y contexto** | `--device`, `-ngl`, `-c` en `start-local-llm.sh` |
| **Puertos** | `8000` en `app.py`; `8080` en `start-local-llm.sh` |
| **Tipos de documento** y sus campos | diccionario `DOC_TYPES` en `documents.py` |
| **Acrónimos jurídicos** reconocidos | diccionario `ABBREVIATIONS` en `app.py` |
| **Comunidades autónomas / rangos** | `REGIONS` y `RANK_LABELS` en `app.py` |
| **Aspecto visual** de la interfaz | `static/index.html` |

---

### Créditos

El Consultor Legislativo (aplicación web, integración IA multi-proveedor y búsqueda semántica) es una contribución de [@nomada1980-IABD](https://github.com/nomada1980-IABD). Herramienta de uso público, libre y abierta, construida sobre el dataset legislativo de Legalize.

> **Nota:** `start-local-llm.sh` está afinado para una GPU **Radeon RX 7600 (Vulkan)** y rutas bajo `~/llamacpp/`. Ajústalo a tu hardware si usas otro dispositivo.

---

## Qué contiene el dataset

- **Constitución** — `es/BOE-A-1978-31229.md`
- **Ley orgánica** — rango: `ley_organica`
- **Ley** — `es/BOE-A-2015-11430.md`
- **Real Decreto-ley** — rango: `real_decreto_ley`
- **Real Decreto Legislativo** — `es/BOE-A-1996-8930.md`
- **Real Decreto** — rango: `real_decreto`
- **Otros rangos estatales** — Orden, Resolución, Circular, Instrucción, Acuerdo, Decreto, Acuerdo internacional
- **Normativa autonómica** (`es-XX/`) — Leyes y decretos de comunidades autónomas según código ELI (`es-pv`, `es-ct`, `es-ga`, etc.), incluidos rangos forales

## Fuente de los datos

- **BOE — Agencia Estatal Boletín Oficial del Estado**
  - Portal: https://www.boe.es
  - Datos abiertos (API): https://www.boe.es/datosabiertos
  - Legislación consolidada: https://www.boe.es/legislacion/legislacion_ava.php
  - Condiciones de reutilización / Aviso legal: https://www.boe.es/informacion/aviso_legal/index.php

## Atribución

> Fuente de los datos: Agencia Estatal Boletín Oficial del Estado (https://www.boe.es). Datos reutilizados conforme a las condiciones de reutilización del BOE (Resolución de 27 de junio de 2024). Este repositorio es una obra derivada basada en datos de la Agencia Estatal Boletín Oficial del Estado.

## Estructura de ficheros

Estructura plana: un directorio por ámbito (`es/` para el Estado; `es-XX/` por comunidad autónoma según código ELI). El rango de la norma figura en el frontmatter YAML, nunca en la ruta del fichero.

## Limitaciones

Las imágenes del texto original se omiten (el proyecto no incorpora activos binarios). Se conserva el texto, las tablas, el formato enriquecido y los metadatos. El identificador del fichero es el ID oficial del BOE.

## Otros países

Este repositorio es parte del proyecto **Legalize**, que mantiene legislación de múltiples países como repos git. Ver https://legalize.dev para el catálogo completo.

## Apoyar

Legalize es libre y abierto. Si este trabajo te resulta útil, puedes ayudar a sostener su alojamiento y desarrollo: [Apoya este proyecto](https://buymeacoffee.com/legalizedev).

## Licencia

- **Código del pipeline**: MIT (https://github.com/legalize-dev/legalize-pipeline)
- **Datos**: Condiciones de reutilización del BOE — cita obligatoria de la fuente
