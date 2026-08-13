# CloudSena

**Transforme sua biblioteca de vídeos em um segundo cérebro pesquisável.**

Plataforma local para organizar vídeos e cursos, transcrever tudo com timestamps e responder
perguntas em português — sempre citando o vídeo e o minuto exato de onde a resposta saiu.

```
Pergunta:  "Onde foi explicado o risco de impermanent loss?"
Resposta:  "O tema aparece no curso Pool de Liquidez, aula 06, entre 14:20 e 19:05 [1].
            A aula compara manter os ativos fora da pool com fornecer liquidez…"
            [1] → abre o player direto em 14:20
```

---

## Como está construído

| Camada | Escolha | Por quê |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind | UI premium, deep links por timestamp, SSE de progresso |
| Backend | FastAPI + SQLAlchemy 2 | assíncrono, tipado, OpenAPI automático em `/docs` |
| Banco | SQLite (WAL) → PostgreSQL | zero setup no MVP, mesma modelagem em produção |
| Busca | FTS5 (BM25) + embeddings, fundidos por RRF | acha tanto o termo literal quanto o significado |
| Fila | tabela no próprio banco, com heartbeat | retomável: reiniciar a máquina não perde trabalho |
| Transcrição | faster-whisper na GPU | roda local, de graça, com timestamps |
| IA | camada de providers plugável | Ollama, OMP, OpenRouter, DeepSeek, Nous, Gemini… |

---

## Instalação

**Requisitos:** Python 3.11+, Node 18+, FFmpeg. GPU NVIDIA é opcional, mas muda tudo na velocidade
da transcrição.

```bash
git clone <seu-repo> cloudsena && cd cloudsena

make setup          # venv Python + node_modules + .env
make doctor         # confere GPU, FFmpeg, Ollama e OMP

# transcrição local na GPU (recomendado)
backend/.venv/bin/pip install faster-whisper

make dev            # API em :8000 e interface em :3000
```

Abra **http://localhost:3000**.

> **Vai rodar num servidor e acessar de outra máquina?**
> Siga [`docs/INSTALACAO_UBUNTU.md`](docs/INSTALACAO_UBUNTU.md) — tem a topologia com nginx,
> os serviços systemd, a transferência dos vídeos e o backup do que não pode ser perdido.

### Rodando o worker separado

Quando a GPU estiver ocupada transcrevendo, a API pode ficar lenta. Separe os processos:

```bash
# terminal 1 — só a API
CLOUDSENA_WORKER_CONCURRENCY=0 make backend

# terminal 2 — só o worker
make worker
```

---

## Primeiros passos na interface

1. **Conexões de IA** → ligue o Ollama e o OMP, clique em *Testar*.
   Se for usar API externa, cole a chave (ela é criptografada no banco e nunca volta ao navegador).
2. **Roteamento por tarefa** → escolha qual modelo faz resumo, qual responde perguntas complexas e
   qual gera embeddings. Cada rota tem fallback automático.
3. **Importar vídeos** → informe o caminho da pasta de cursos. O CloudSena mostra uma prévia do que
   encontrou antes de confirmar. **Seus arquivos nunca são copiados nem movidos.**
4. **Processamento** → acompanhe a fila em tempo real.
5. **Perguntar** → faça a pergunta e clique nas citações para abrir o minuto exato.

---

## Providers suportados

**Locais (custo zero, nada sai da máquina):** Ollama · OMP / Oh-my-pi · LM Studio · vLLM/TGI · llama.cpp

**APIs:** OpenRouter · DeepSeek · Nous Research · OpenAI · Anthropic · Google Gemini · Groq ·
Together · Mistral · Fireworks · xAI · Cerebras · Perplexity · qualquer endpoint OpenAI-compatible

Adicionar um provider novo é uma entrada em `backend/app/providers/catalog.py`. Se ele falar o
padrão OpenAI, não precisa escrever código nenhum.

### Roteamento sugerido para a máquina do projeto (i3 + 28 GB + RTX 3060 Ti)

| Tarefa | Motor |
|---|---|
| Transcrição | faster-whisper `large-v3` local na GPU |
| Resumo em lote | DeepSeek Flash via OMP |
| Capítulos e tags | DeepSeek Flash via OMP |
| Perguntas complexas | DeepSeek Pro via OMP → fallback OpenRouter |
| Análise visual | Gemini Flash |
| Embeddings | `nomic-embed-text` via Ollama |
| Fallback privado | Qwen 2.5 7B via Ollama |

Já vem configurado assim no primeiro boot. Mude quando quiser em *Conexões de IA*.

---

## Modos de privacidade

Definidos por biblioteca — dá para ter cursos internos em modo Local e cursos públicos em Híbrido.

- **Local** — Whisper, embeddings e respostas rodam na sua máquina. Nada trafega.
- **Híbrido** *(padrão)* — vídeos e transcrição ficam locais; só os trechos recuperados vão para a API.
- **Nuvem** — processamento remoto autorizado, para a versão comercial.

Em qualquer modo: as chaves ficam criptografadas (Fernet) no banco, os logs são filtrados para não
registrar segredos, e os vídeos são referenciados por caminho e hash — nunca duplicados.

---

## A regra que sustenta o produto

> O assistente responde **somente** com base nos trechos recuperados. Quando não há evidência
> suficiente, ele diz que não encontrou — em vez de inventar.

Está no prompt (`backend/app/services/prompts.py`) e é verificada no código: a resposta só é marcada
como *ancorada* se citar fontes reais recuperadas do índice. A UI mostra esse selo em toda resposta.

---

## Estrutura

```
cloudsena/
├── backend/
│   └── app/
│       ├── api/routes/     libraries, sources, videos, chat, providers, system
│       ├── core/           logging, criptografia, barramento SSE
│       ├── db/             modelos, sessão, migração inicial + seed
│       ├── providers/      catálogo, OpenAI-compatible, Ollama, Gemini, Anthropic, registry
│       ├── services/       media, scanner, transcription, chunking, embeddings, search, rag
│       └── workers/        fila retomável, pipeline, runner
├── frontend/
│   ├── app/                painel, biblioteca, vídeo, perguntar, fila, conexões
│   ├── components/         player+transcrição, citações, cards, diálogos
│   └── lib/                cliente da API tipado
├── data/                   banco, thumbnails, transcrições, frames, logs (fora do git)
├── docs/                   arquitetura, roadmap, plano comercial
└── scripts/                doctor.sh
```

---

## Pipeline de processamento

```
descoberto → na fila → extraindo áudio → transcrevendo → resumindo → indexando → pronto
                                              ↓
                                            falhou (repetível individualmente)
```

Cada etapa é idempotente e checa se já foi concluída. Reiniciou a máquina no meio? O job volta para
a fila e continua do último estágio salvo. Vídeo duplicado (mesmo hash) não é reprocessado — só o
caminho é atualizado.

---

## API

Documentação interativa em **http://localhost:8000/docs**.

```bash
# Buscar trechos (sem LLM — rápido e de graça)
curl -X POST localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"impermanent loss","library_id":1}'

# Perguntar com citações
curl -X POST localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Onde foi explicado impermanent loss?","library_id":1}'
```

---

## Caminho comercial

Ver [`docs/COMERCIAL.md`](docs/COMERCIAL.md). Em resumo: o mesmo código atende o app local premium
(licença única), o SaaS (assinatura) e a versão para equipes — porque autenticação, multi-biblioteca,
limites de uso e telemetria já têm lugar reservado na modelagem.

## Licença

Proprietário. Todos os direitos reservados.
