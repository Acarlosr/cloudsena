#!/usr/bin/env bash
# Diagnóstico do ambiente do CloudSena.
# Uso: bash scripts/doctor.sh

set -uo pipefail

ok()   { printf "  \033[32m✔\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✘\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
head_() { printf "\n\033[1m%s\033[0m\n" "$1"; }

printf "\n\033[1;35m CloudSena — diagnóstico do ambiente\033[0m\n"

head_ "Sistema"
ok "$(uname -srm)"
command -v python3 >/dev/null && ok "Python $(python3 -V 2>&1 | cut -d' ' -f2)" || bad "Python 3 não encontrado"
command -v node >/dev/null && ok "Node $(node -v)" || bad "Node.js não encontrado (necessário para o frontend)"

head_ "Mídia"
if command -v ffmpeg >/dev/null; then
  ok "FFmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"
else
  bad "FFmpeg ausente — sudo apt install ffmpeg"
fi
command -v ffprobe >/dev/null && ok "ffprobe disponível" || bad "ffprobe ausente"

head_ "GPU"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version \
    --format=csv,noheader | while IFS= read -r line; do ok "$line"; done
  python3 - <<'PY' 2>/dev/null || warn "ctranslate2 não instalado (vem com faster-whisper)"
import ctranslate2
n = ctranslate2.get_cuda_device_count()
print(f"  \033[32m✔\033[0m CUDA visível para o CTranslate2: {n} dispositivo(s)")
PY
else
  warn "nvidia-smi ausente — a transcrição vai rodar em CPU (bem mais lenta)"
fi

head_ "Transcrição"
python3 -c "import faster_whisper" 2>/dev/null \
  && ok "faster-whisper instalado" \
  || bad "faster-whisper ausente — pip install faster-whisper"

head_ "Motores de IA locais"
OLLAMA_URL="${CLOUDSENA_OLLAMA_BASE_URL:-http://localhost:11434}"
if curl -sf --max-time 3 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  count=$(curl -s --max-time 3 "$OLLAMA_URL/api/tags" | grep -o '"name"' | wc -l | tr -d ' ')
  ok "Ollama respondendo em $OLLAMA_URL ($count modelo(s))"
  curl -s --max-time 3 "$OLLAMA_URL/api/tags" \
    | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | sed 's/^/      · /'
else
  warn "Ollama não respondeu em $OLLAMA_URL (ollama serve)"
fi

OMP_URL="${CLOUDSENA_OMP_BASE_URL:-http://localhost:8080/v1}"
if curl -sf --max-time 3 "$OMP_URL/models" >/dev/null 2>&1; then
  ok "OMP respondendo em $OMP_URL"
  curl -s --max-time 3 "$OMP_URL/models" \
    | grep -o '"id":"[^"]*"' | cut -d'"' -f4 | head -8 | sed 's/^/      · /'
else
  warn "OMP não respondeu em $OMP_URL — ajuste CLOUDSENA_OMP_BASE_URL no .env"
fi

head_ "CloudSena"
if curl -sf --max-time 3 http://localhost:8000/api/health >/dev/null 2>&1; then
  ok "API no ar em http://localhost:8000"
else
  warn "API parada — rode: make backend"
fi

printf "\nPróximo passo: \033[36mmake dev\033[0m e abra http://localhost:3000\n\n"
