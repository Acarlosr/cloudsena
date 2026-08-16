<div align="center">

# CloudSena

**Transforme sua biblioteca de vídeos em um segundo cérebro pesquisável.**

Transcreve tudo com timestamp. Responde em português. Sempre cita o vídeo e o minuto exato —
nunca inventa.

[![Local-first](https://img.shields.io/badge/local--first-privacidade%20por%20padrão-6366f1)](#modos-de-privacidade)
[![Stack](https://img.shields.io/badge/stack-Next.js%20%2B%20FastAPI-111827)](#como-está-construído)
[![Licença](https://img.shields.io/badge/licença-proprietária-000000)](LICENSE)

</div>

---

```
Pergunta:  "Onde foi explicado o risco de impermanent loss?"
Resposta:  "O tema aparece no curso Pool de Liquidez, aula 06, entre 14:20 e 19:05 [1].
            A aula compara manter os ativos fora da pool com fornecer liquidez…"
            [1] → abre o player direto em 14:20
```

Isso é o produto inteiro em uma imagem: **prova, não resumo**. Um chatbot genérico responde
qualquer coisa com confiança. O CloudSena só responde com base no que está de fato nos seus
vídeos — e mostra exatamente de onde tirou.

---

## O que é isto

Um aplicativo local. Roda na sua máquina (ou no seu servidor), sobre a sua biblioteca de vídeos —
cursos comprados, gravações de aula, playlists do YouTube que você acompanha. Não é um app na
nuvem que você assina, nem um produto blockchain/Web3 — é software que você instala e é dono dos
dados o tempo todo.

A arquitetura foi desenhada para, no futuro, também rodar como serviço hospedado (SaaS) sem
reescrever nada — mas hoje, do jeito que está, é local-first: vídeo, banco de dados, transcrição e
busca ficam na sua máquina. Só o que você decidir mandar para uma API de IA sai daqui.

---

## Como está construído

| Camada | Escolha | Por quê |
|---|---|---|
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind | UI premium, deep links por timestamp, tempo real |
| Backend | FastAPI + SQLAlchemy 2 | assíncrono, tipado, documentação automática em `/docs` |
| Banco | SQLite (WAL) → PostgreSQL | zero setup agora, mesma modelagem em produção depois |
| Busca | FTS5 (BM25) + embeddings, fundidos por RRF | acha tanto o termo literal quanto o significado |
| Fila | tabela no próprio banco, com heartbeat | retomável — reiniciar a máquina não perde trabalho |
| Transcrição | faster-whisper na GPU | roda local, de graça, com timestamps |
| Importação | pasta local ou playlist do YouTube | baixa só o áudio de vídeos do YouTube, nunca o vídeo inteiro |
| IA | camada de providers plugável | Ollama, OMP, OpenRouter, DeepSeek, Nous Research, Gemini… |

---

## Instalação

**Requisitos:** Python 3.11+, Node 18+, FFmpeg. GPU NVIDIA é opcional, mas muda tudo na velocidade
da transcrição.

```bash
git clone <seu-repo> cloudsena && cd cloudsena

make setup          # venv Python + node_modules + .env
make doctor         # confere GPU, FFmpeg, Ollama, OMP e modelo de embeddings

make dev            # API em :8000 e interface em :3000
```

Abra **http://localhost:3000**.

> **Vai rodar num servidor e acessar de outra máquina?**
> Siga [`docs/INSTALACAO_UBUNTU.md`](docs/INSTALACAO_UBUNTU.md) — tem a topologia com nginx, os
> serviços systemd (pra ligar sozinho quando o servidor reiniciar), a transferência dos vídeos e o
> backup do que não pode ser perdido.

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

1. **Conexões de IA** → ligue o Ollama, clique em *Testar*. Se for usar API externa (OpenRouter,
   Nous, DeepSeek…), cole a chave — ela é criptografada no banco e nunca volta ao navegador.
2. **Roteamento por tarefa** → escolha qual modelo faz resumo, qual responde perguntas complexas e
   qual gera embeddings. Cada rota tem fallback automático — sem chave configurada, cai pro Ollama
   local sozinho, nada quebra.
3. **Importar vídeos** → pasta local ou playlist do YouTube. Pasta local: seus arquivos nunca são
   copiados nem movidos. Playlist do YouTube: só o áudio é baixado (nunca o vídeo), e é descartado
   depois de transcrito.
4. **Processamento** → acompanhe a fila em tempo real.
5. **Perguntar** → faça a pergunta e clique nas citações para abrir o minuto exato.

---

## Providers de IA suportados

**Locais (custo zero, nada sai da máquina):** Ollama · OMP / Oh-my-pi · LM Studio · vLLM/TGI ·
llama.cpp

**APIs:** OpenRouter · DeepSeek · Nous Research · OpenAI · Anthropic · Google Gemini · Groq ·
Together · Mistral · Fireworks · xAI · Cerebras · Perplexity · qualquer endpoint OpenAI-compatível

Adicionar um provider novo é uma entrada em `backend/app/providers/catalog.py`. Se ele falar o
padrão OpenAI, não precisa escrever código nenhum.

---

## Modos de privacidade

Definidos por biblioteca — dá para ter cursos internos em modo Local e cursos públicos em Híbrido,
ao mesmo tempo.

| Modo | O que acontece |
|---|---|
| **Local** | Whisper, embeddings e respostas rodam na sua máquina. Nada trafega. |
| **Híbrido** *(padrão)* | vídeo e transcrição ficam locais; só os trechos recuperados vão para a API. |
| **Nuvem** | processamento remoto autorizado — para a versão comercial. |

Em qualquer modo: chaves de API ficam criptografadas (Fernet) no banco, os logs são filtrados pra
nunca registrar segredo, e os vídeos são referenciados por caminho e hash — nunca duplicados.

---

## A regra que sustenta o produto

> O assistente responde **somente** com base nos trechos recuperados. Quando não há evidência
> suficiente, ele diz que não encontrou — em vez de inventar.

Está no prompt (`backend/app/services/prompts.py`) **e** é verificada no código: a resposta só é
marcada como *ancorada* se citar fontes reais recuperadas do índice. A interface mostra esse selo
em toda resposta.

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

## Estrutura

```
cloudsena/
├── backend/
│   └── app/
│       ├── api/routes/     libraries, sources, videos, chat, providers, system
│       ├── core/           logging, criptografia, barramento de eventos em tempo real
│       ├── db/             modelos, sessão, migração inicial + seed
│       ├── providers/      catálogo, OpenAI-compatible, Ollama, Gemini, Anthropic, registry
│       ├── services/       media, scanner, youtube, transcription, chunking, embeddings, search, rag
│       └── workers/        fila retomável, pipeline, runner
├── frontend/
│   ├── app/                painel, biblioteca, vídeo, perguntar, fila, conexões
│   ├── components/         player local + player do YouTube, transcrição, citações, cards
│   └── lib/                cliente da API tipado
├── data/                   banco, thumbnails, transcrições, logs (fora do git)
├── docs/                   arquitetura, roadmap, plano comercial, instalação em servidor
└── deploy/                 systemd + nginx pra rodar como serviço permanente
```

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

## Histórico de mudanças

Ver [`CHANGELOG.md`](CHANGELOG.md).

## Licença

Proprietário. Todos os direitos reservados. Ver [`LICENSE`](LICENSE).
