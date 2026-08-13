# Roadmap

Estado atual: **Fases 0, 1 e 2 implementadas.** Abaixo, o que existe e o que vem.

---

## ✅ Fase 0 — Validação técnica

- [x] `make doctor` verifica GPU, CUDA, FFmpeg, Ollama e OMP
- [x] Probe de mídia, thumbnails e extração de áudio
- [x] Integração com faster-whisper (GPU, com fallback para CPU)
- [x] OMP e Ollama acessíveis fora do terminal, pela interface
- [x] Medição de custo e latência por chamada (`UsageLog`)

## ✅ Fase 1 — MVP pessoal

- [x] Interface local premium (Next.js)
- [x] Cadastro de pastas com prévia antes de importar
- [x] Catálogo em cards com filtros, ordenação e favoritos
- [x] Thumbnails automáticas
- [x] Player local com HTTP Range (pula direto para o minuto)
- [x] Transcrição com timestamps
- [x] Resumo curto e detalhado
- [x] Busca textual (FTS5/BM25)

## ✅ Fase 2 — Biblioteca inteligente

- [x] Embeddings e busca semântica
- [x] Busca híbrida com fusão RRF
- [x] Perguntas por vídeo, curso ou biblioteca inteira
- [x] Respostas com citação clicável até o minuto
- [x] Capítulos automáticos e navegáveis
- [x] Transcrição sincronizada com o player
- [x] Favoritos, notas, progresso de estudo
- [x] Fila retomável com recuperação de jobs órfãos
- [x] Progresso em tempo real (SSE)
- [x] Painel de providers com roteamento por tarefa e fallback

---

## ⬜ Fase 3 — YouTube

- [ ] OAuth com Google
- [ ] Importação de playlists do usuário
- [ ] Sincronização manual e agendada
- [ ] Atualização de metadados e detecção de vídeos removidos/privados
- [ ] Transcrição: usar legendas oficiais quando existirem (mais rápido e barato) e cair no Whisper quando não

> Base pronta: `SourceType.youtube`, `Video.youtube_id`, `Video.channel` e `Source.sync_status` já
> existem no modelo. Falta o cliente da API e o worker de sincronização.

## ⬜ Fase 4 — Qualidade premium

- [ ] Análise visual de frames (slides, código na tela, gráficos) — `media.extract_frames` já existe
- [ ] OCR do que aparece na tela
- [ ] Mapa de conceitos da biblioteca
- [ ] Comparação entre aulas ("o que a aula 7 acrescenta à 5?")
- [ ] Edição manual da transcrição, com reindexação do trecho
- [ ] Avaliação automática das respostas (dataset de regressão)
- [ ] Histórico de versões de resumo e transcrição — `version` já existe nas tabelas

## ⬜ Fase 5 — Produto comercial

- [ ] Usuários e autenticação
- [ ] Organizações e permissões por biblioteca
- [ ] Cobrança e limites de uso
- [ ] Painel administrativo
- [ ] Instalador (Docker Compose + desktop)
- [ ] Telemetria opcional
- [ ] Documentação de instalação em servidor próprio

---

## Critérios de "pronto" (do documento original)

| Critério | Status |
|---|---|
| Encontrar um assunto em menos de 30 s | ✅ busca híbrida + citação direta |
| Respostas mostram a origem | ✅ citações com vídeo, capítulo e intervalo |
| Timestamp abre no trecho correto | ✅ HTTP Range + deep link `?t=` |
| Reiniciar a máquina sem perder a fila | ✅ jobs retomáveis com heartbeat |
| Vídeos duplicados não reprocessam | ✅ hash parcial (início/meio/fim + tamanho) |
| Erros repetíveis individualmente | ✅ botão por vídeo e por job |
| Saber quando a resposta não está no conteúdo | ✅ selo "sem evidência" + texto explícito |
| Não inventar resposta sem indicar falta de evidência | ✅ regra no prompt + verificação de citações |

---

## Próximo passo prático

1. `make setup && make doctor` no servidor Ubuntu.
2. `pip install faster-whisper` e processar **um curso real inteiro**.
3. Anotar: tempo de transcrição por hora de vídeo, custo por hora em cada rota, taxa de falha.
4. Fazer 20 perguntas cujas respostas você já conhece e medir quantas vêm ancoradas e corretas.
5. Só então decidir preço e qual dos três produtos comerciais atacar primeiro.
