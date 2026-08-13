# Arquitetura do CloudSena

Documento técnico: por que cada peça está onde está, e o que muda quando o produto crescer.

---

## 1. Princípios que guiaram as decisões

1. **Local primeiro.** O usuário deve conseguir rodar tudo sem uma única chave de API.
2. **Rastreabilidade acima de fluência.** Uma resposta bonita sem fonte é um bug.
3. **Nunca duplicar vídeo.** Arquivos são referenciados por caminho + hash.
4. **Retomável por padrão.** Desligar a máquina no meio de 40 h de curso não pode custar o trabalho já feito.
5. **Trocar de motor não pode exigir refatoração.** Daí a camada de providers.
6. **O MVP já é a arquitetura final.** SQLite vira Postgres, fila em tabela vira Celery — sem reescrever o domínio.

---

## 2. Fluxo de dados

```
   pasta local ──┐
                 ├──► scanner ──► Video(discovered) ──► Job(full_pipeline)
   playlist YT ──┘                                             │
                                                               ▼
                                             ┌──────── worker (runner.py) ────────┐
                                             │ probe    → duração, thumbnail      │
                                             │ extract  → wav mono 16 kHz         │
                                             │ transcribe → faster-whisper (GPU)  │
                                             │ enrich   → resumo, capítulos, tags │
                                             │ index    → chunks + embeddings     │
                                             └────────────────┬───────────────────┘
                                                              ▼
                                              FTS5 (BM25)  +  vetores float32
                                                              │
   pergunta ──► busca híbrida ──► RRF ──► rerank ──► contexto ──► LLM ──► resposta + citações
```

---

## 3. Por que busca híbrida com RRF

A busca puramente semântica erra em nomes próprios, siglas e comandos (`WHERE`, `useEffect`,
`impermanent loss`). A puramente lexical erra quando o aluno pergunta com outras palavras. Rodamos as
duas e fundimos com **Reciprocal Rank Fusion**:

```
score(d) = Σ  peso_sistema / (60 + posição_no_ranking)
```

RRF usa apenas a *posição*, então não é preciso normalizar escores de sistemas incomparáveis
(BM25 vs. cosseno). É robusto, tem um único parâmetro e funciona bem sem calibração.

Depois vem um rerank opcional por LLM sobre os ~24 melhores candidatos. Se o rerank falhar ou estiver
desligado, a ordem híbrida é usada — a busca **nunca** cai por causa disso.

## 4. Por que os vetores ficam no SQLite

Para uma biblioteca pessoal (dezenas de milhares de trechos), carregar os vetores em uma matriz
NumPy e fazer produto interno leva milissegundos e evita mais um serviço para instalar, versionar e
fazer backup. Os embeddings são gravados como `float32` bruto em `BLOB`.

Quando migrar: o modelo `TranscriptChunk` já tem `embedding_model` e `embedding_dim`, então trocar
para pgvector ou Qdrant é reescrever apenas `services/embeddings.py:load_matrix` e `cosine_search`.
O limite prático dessa abordagem fica na casa de ~200 mil trechos (~600 MB de vetores em RAM).

## 5. Chunking

Agrupa segmentos do Whisper até ~1100 caracteres, preferindo cortar em fim de frase, com 180
caracteres de sobreposição. O timestamp de início e fim vem do próprio segmento — é isso que permite
a citação apontar para o minuto certo. Cada trecho guarda também o capítulo, o que deixa a citação
legível ("aula 06, capítulo *Cálculo da perda*").

## 6. A fila

Uma tabela `jobs` com claim atômico (`UPDATE ... WHERE status='pending'` e checagem de `rowcount`),
`heartbeat_at` e política de tentativas. Jobs `running` sem heartbeat há mais de 15 minutos voltam
para `pending` — é assim que um desligamento abrupto se resolve sozinho no próximo boot.

Trocar por Celery/RQ depois é só reimplementar `claim_next`; `pipeline.execute` não muda.

## 7. A camada de providers

```
AIProvider (Protocol)
├── OpenAICompatibleProvider   → OpenRouter, DeepSeek, Nous, OMP, Groq, LM Studio, vLLM, …
├── OllamaProvider             → API nativa (/api/chat, /api/embed, /api/ps)
├── GeminiProvider             → generateContent + embedContent
└── AnthropicProvider          → Messages API
```

Acima delas, o **registry** resolve `tarefa → (provider, modelo, parâmetros)` consultando as
`RoutingRule`, com fallback automático e registro de uso (tokens, custo, latência, sucesso). Toda
chamada de IA do sistema passa por `registry.complete()` — nenhum serviço fala com um provider
diretamente. É isso que faz "trocar o motor de resumo" ser um `<select>` na interface.

Um provider novo compatível com OpenAI custa **uma entrada no catálogo**, zero código.

## 8. Segurança

- Chaves criptografadas com Fernet; a chave-mestra vem do `.env` ou de `data/database/.secret.key` (0600).
- O frontend só recebe máscara (`sk-or-••••••9f2a`); a chave nunca volta pela API.
- `RedactFilter` no logging remove padrões de chave antes de escrever no arquivo.
- `X-CloudSena-Token` opcional protege a API quando exposta na rede.
- O streaming de vídeo serve apenas caminhos registrados no banco — não aceita caminho arbitrário.

## 9. Streaming de vídeo

`GET /api/videos/{id}/stream` implementa HTTP Range (206 Partial Content). Sem isso o navegador
baixaria o arquivo inteiro antes de pular para 14:20 — o que quebraria a promessa central do produto
em cursos de 2 GB.

## 10. Tempo real

Um `EventBus` em memória publica eventos (`job.progress`, `video.status`, `source.scanned`) e a rota
`/api/events` os entrega por SSE, com keepalive a cada 20 s e replay opcional. O worker publica de
outra thread via `publish_threadsafe`. O frontend reconecta sozinho.

SSE (e não WebSocket) porque o fluxo é unidirecional, atravessa proxy sem configuração e reconecta
nativamente.

## 11. O que muda na versão comercial

| Hoje | Depois | Onde mexer |
|---|---|---|
| SQLite | PostgreSQL | só `CLOUDSENA_DATABASE_URL` (FTS5 cai no fallback `ilike`; use `tsvector`) |
| Sessão local | usuários + organizações | `Library.owner_id` já existe; adicionar `User`, `Org` e dependência de auth |
| Fila em tabela | Celery + Redis | reimplementar `queue.claim_next` |
| Vetores em BLOB | pgvector / Qdrant | `embeddings.load_matrix` e `cosine_search` |
| Sem limites | cotas por plano | `UsageLog` já registra tokens, custo e latência por tarefa |
| Arquivos locais | S3/MinIO | `Video.file_path` vira URI; `media.py` ganha um resolvedor |
