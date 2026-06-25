#!/usr/bin/env bash
# Arranca el modelo de IA local (Qwen2.5-7B) en la GPU Radeon RX 7600 vía
# llama.cpp (backend Vulkan). Expone una API OpenAI-compatible en :8080.
#
# Uso:   ./start-local-llm.sh
# Logs:  ~/llamacpp/server.log
set -euo pipefail

LLAMA_DIR="$HOME/llamacpp/llama-b9581"
PORT=8080
export LD_LIBRARY_PATH="$LLAMA_DIR:${LD_LIBRARY_PATH:-}"

# ¿El puerto ya está ocupado? (otra instancia viva) -> avisa en vez de fallar feo.
EXISTING_PID=$(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oE 'pid=[0-9]+' | cut -d= -f2 | head -1 || true)
if [ -n "${EXISTING_PID:-}" ]; then
  echo "⚠️  El puerto $PORT ya está en uso por el PID $EXISTING_PID (¿ya tienes el modelo arrancado?)."
  echo "    Para detenerlo de forma segura:  kill $EXISTING_PID"
  echo "    (No uses 'pkill -f llama-server': el patrón se mata a sí mismo.)"
  exit 1
fi

# --device Vulkan1 = RX 7600 dedicada (Vulkan0 es la iGPU integrada del Ryzen).
# -ngl 99  -> todas las capas a la GPU.  -c 8192 -> ventana de contexto.
#
# --skip-chat-parsing: clave para la estabilidad. Por defecto llama-server usa la
# plantilla Jinja de Qwen2.5 con su parser de tool-calls "peg-native", que
# devuelve HTTP 500 ("Failed to parse tool call arguments as JSON") cuando el
# modelo emite JSON o respuestas largas cortadas por max_tokens. Con este flag se
# fuerza un parser de contenido puro: la respuesta llega tal cual en
# message.content (no necesitamos tool-calls), sin ese fallo intermitente.
exec "$LLAMA_DIR/llama-server" \
  -hf bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M \
  --device Vulkan1 \
  --host 127.0.0.1 --port 8080 \
  -ngl 99 -c 8192 --jinja --skip-chat-parsing
