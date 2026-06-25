#!/usr/bin/env bash
# Inicia el Consultor Legislativo España
set -e

cd "$(dirname "$0")"

# Instala dependencias si faltan
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
  echo "Instalando dependencias..."
  pip3 install -q -r requirements.txt
fi

AI_INFO="IA LOCAL en GPU (${LOCAL_LLM_URL:-http://127.0.0.1:8080/v1})"
echo "Iniciando/verificando modelo local..."
./start-local-llm.sh > "$HOME/llamacpp/server.log" 2>&1 &
sleep 2

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   Consultor Legislativo España             ║"
echo "║   http://localhost:8000                    ║"
echo "║                                            ║"
echo "║   • El índice se construye en segundo      ║"
echo "║     plano (primera vez ~60-90 s)           ║"
echo "║   • Ctrl+C para detener                    ║"
echo "╚════════════════════════════════════════════╝"
echo "   IA: $AI_INFO"
echo ""

python3 app.py
