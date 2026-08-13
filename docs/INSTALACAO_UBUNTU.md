# Instalação no servidor Ubuntu

Cenário deste guia: **tudo roda no Ubuntu** (vídeos, banco, transcrição, IA) e você acessa de outra
máquina pelo navegador.

```
   Mac / celular                     Servidor Ubuntu (RTX 3060 Ti)
   ┌───────────┐                     ┌──────────────────────────────────┐
   │ navegador │ ──── rede local ──► │ nginx :80                        │
   └───────────┘                     │   ├─► Next.js  127.0.0.1:3000    │
                                     │   └─► FastAPI  127.0.0.1:8000    │
                                     │         ├─ worker (GPU)          │
                                     │         ├─ Ollama :11434         │
                                     │         └─ OMP :8080             │
                                     │   vídeos em /srv/cloudsena/videos│
                                     └──────────────────────────────────┘
```

**Princípio de segurança:** a API e o Next escutam só em `127.0.0.1`. O único processo exposto na
rede é o nginx. O que não escuta na rede não pode ser chamado dela — por isso aqui não é preciso
`CLOUDSENA_API_TOKEN`.

---

## 1. Dependências do sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip ffmpeg git nginx curl

# Node 20 (o do apt costuma ser velho demais para o Next 14)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

node -v && python3 -V && ffmpeg -version | head -1
```

Driver NVIDIA e CUDA já devem estar funcionando. Confirme com `nvidia-smi`.

## 2. Código no lugar

```bash
sudo mkdir -p /srv/cloudsena
sudo chown $USER:$USER /srv/cloudsena
git clone <seu-repo> /srv/cloudsena
cd /srv/cloudsena

make setup            # venv + node_modules + .env
backend/.venv/bin/pip install faster-whisper
make doctor           # confere GPU, CUDA, FFmpeg, Ollama e OMP
```

Resolva tudo que o `doctor` apontar **antes** de seguir. É mais barato agora.

## 3. Ajustar o `.env`

```bash
nano /srv/cloudsena/.env
```

```ini
CLOUDSENA_ENVIRONMENT=production
CLOUDSENA_DEBUG=false

# A API só escuta local; quem atende a rede é o nginx.
CLOUDSENA_HOST=127.0.0.1
CLOUDSENA_DATA_DIR=/srv/cloudsena/data

# Gere a sua e GUARDE UMA CÓPIA (é ela que descriptografa suas chaves de API):
#   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CLOUDSENA_SECRET_KEY=cole-a-chave-gerada-aqui

# RTX 3060 Ti (8 GB): large-v3 em float16 cabe.
# Se der falta de VRAM, troque para distil-large-v3 ou medium.
CLOUDSENA_WHISPER_MODEL=large-v3
CLOUDSENA_WHISPER_DEVICE=cuda
CLOUDSENA_WHISPER_COMPUTE_TYPE=float16

CLOUDSENA_OLLAMA_BASE_URL=http://localhost:11434
CLOUDSENA_OMP_BASE_URL=http://localhost:8080/v1

# 1 worker: a transcrição já ocupa a GPU inteira.
CLOUDSENA_WORKER_CONCURRENCY=1
```

## 4. Levar os vídeos para o servidor

Do Mac, com `rsync` (retoma de onde parou se cair):

```bash
rsync -avh --progress --partial \
  "/Volumes/Curso/Meus Cursos/" \
  usuario@ip-do-ubuntu:/srv/cloudsena/videos/
```

A estrutura de pastas vira a categorização: **uma pasta por curso**, subpastas viram módulos, e o
número no início do arquivo (`01 - intro.mp4`) vira a ordem da aula. Vale organizar antes de importar.

Confira que o usuário que roda o worker consegue ler tudo:

```bash
sudo chown -R $USER:$USER /srv/cloudsena/videos
```

## 5. Build e serviços

```bash
cd /srv/cloudsena/frontend && npm run build

cd /srv/cloudsena
sudo cp deploy/cloudsena.service        /etc/systemd/system/
sudo cp deploy/cloudsena-worker.service /etc/systemd/system/
sudo cp deploy/cloudsena-web.service    /etc/systemd/system/

# Troque %i pelo seu usuário nos três arquivos:
sudo sed -i "s/^User=%i/User=$USER/" /etc/systemd/system/cloudsena*.service

sudo systemctl daemon-reload
sudo systemctl enable --now cloudsena cloudsena-worker cloudsena-web
systemctl status cloudsena cloudsena-worker cloudsena-web --no-pager
```

## 6. Nginx

```bash
sudo cp /srv/cloudsena/deploy/nginx.conf /etc/nginx/sites-available/cloudsena
sudo ln -sf /etc/nginx/sites-available/cloudsena /etc/nginx/sites-enabled/cloudsena
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo ufw allow 80/tcp     # se o firewall estiver ativo
```

Descubra o IP do servidor com `hostname -I`. No navegador do Mac: **http://IP-DO-UBUNTU**.

Para usar um nome em vez do IP, no Mac: `sudo nano /etc/hosts` e acrescente
`192.168.x.x   cloudsena.local`.

## 7. Primeiro uso

1. **Conexões de IA** → teste Ollama e OMP. Se algum falhar, o `status_message` no card diz o motivo.
2. **Roteamento por tarefa** → confira os modelos. O padrão já assume DeepSeek Flash via OMP para
   lote e DeepSeek Pro para perguntas complexas.
3. Se for usar embeddings via Ollama: `ollama pull nomic-embed-text`.
4. **Importar vídeos** → caminho `/srv/cloudsena/videos/Nome Do Curso`. Comece por **um curso só**.
5. Acompanhe em **Processamento**.

---

## Operação do dia a dia

```bash
# logs ao vivo
journalctl -u cloudsena-worker -f
journalctl -u cloudsena -f

# reiniciar depois de um git pull
cd /srv/cloudsena && git pull
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && npm run build
sudo systemctl restart cloudsena cloudsena-worker cloudsena-web

# GPU durante a transcrição
watch -n2 nvidia-smi
```

## Backup

O que é insubstituível é pequeno; o que é grande se regenera.

```bash
# ESSENCIAL — banco, chave de criptografia, transcrições e resumos
tar czf ~/cloudsena-backup-$(date +%F).tar.gz \
    -C /srv/cloudsena data/database data/transcripts data/summaries .env
```

`data/thumbnails`, `data/frames` e `data/temp` não precisam de backup: são recriados.

> **`data/database/.secret.key` é o arquivo mais importante do sistema.** Sem ele, as chaves de API
> guardadas no banco não podem ser descriptografadas. Nada mais se perde — mas você teria que
> recadastrar todas.

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `CUDA out of memory` na transcrição | `large-v3` + outro modelo ocupando VRAM | `CLOUDSENA_WHISPER_MODEL=distil-large-v3`, ou `ollama stop <modelo>` antes do lote |
| Vídeos ficam em "Na fila" para sempre | worker parado | `systemctl status cloudsena-worker` e veja o journal |
| Progresso não atualiza sozinho | SSE bloqueado por proxy | confirme o bloco `location /api/events` no nginx |
| Player não pula para o minuto | Range não chegou ao backend | confirme `proxy_set_header Range` no nginx |
| "Nenhum provider habilitado" | nenhum motor ligado | Conexões de IA → ligar Ollama/OMP → Testar |
| Busca acha pouco | embeddings não geraram | `ollama pull nomic-embed-text` e reprocessar |
| Transcrição muito lenta | rodando em CPU | `make doctor`; se CUDA não aparecer, reinstale `faster-whisper` |
