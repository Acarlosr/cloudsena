# Changelog

Formato livre, em português, focado em decisão e motivo — não só "o que mudou".

## [Não lançado] — split OpenRouter/Nous por preço real (15/08/2026)

### Alterado

- **`chat` e `chat_complex` passaram de OpenRouter para o Nous Research
  Portal**, mantendo o mesmo modelo (DeepSeek V4 Pro 0813). Motivo é só preço:
  no Nous Portal esse modelo custa $0,35/$0,70 (in/out por 1M tokens) contra
  $0,44/$0,87 no OpenRouter — ~20% mais barato. Já o V4 Flash 0731 (usado em
  `summarize`/`chapters`/`tags`/`rerank`/`title`) é o inverso: $0,08/$0,16 no
  OpenRouter contra $0,11/$0,22 no Nous Portal — por isso essas rotas continuam
  no OpenRouter. Preço por provider muda com frequência; vale reconferir de vez
  em quando em vez de fixar por hábito. O provider `nous` já existia no
  catálogo (`providers/catalog.py`) — só precisou apontar a rota pra ele.
- Lista de modelos sugeridos do provider `nous` atualizada: além do Hermes
  próprio, o portal hoje revende outros modelos (DeepSeek incluso) — antes só
  listava Hermes.

## [Não lançado] — roteamento via OpenRouter (15/08/2026)

### Alterado

- **Rotas padrão passaram a usar DeepSeek V4 via OpenRouter**, com Ollama como
  fallback automático (não como padrão). Critério de divisão: tarefas de volume
  alto e formato fechado — `summarize`, `chapters`, `tags`, `rerank`, `title`,
  que rodam em todo vídeo importado — vão no **V4 Flash** (`deepseek-v4-flash-0731`,
  ~5x mais barato). `chat` e `chat_complex` — a pergunta do usuário, onde mora a
  citação `[n]` que sustenta a promessa de "não inventar" — vão no **V4 Pro**
  (`deepseek-v4-pro-0813`), onde o raciocínio mais forte compensa o custo maior
  (ainda assim, poucos centavos por milhares de perguntas). `embeddings` continua
  fixo no Ollama local — não é decisão de custo: toda busca depende dele com
  latência de rede, e trocar de modelo de embedding exige reindexar a biblioteca
  inteira (vetores de dimensão diferente são descartados). Como o provider
  `openrouter` só é ativado quando a chave é colada em *Conexões de IA*, até lá
  `registry.resolve()` cai pro Ollama sozinho — não quebra o primeiro boot de
  quem ainda não tem a chave, mesma rede de segurança do ajuste anterior.
- Lista de modelos sugeridos do OpenRouter (`providers/catalog.py`) atualizada —
  tinha `deepseek-r1` e `hermes-3` como sugestão, desatualizados frente aos
  modelos atuais (`deepseek-v4-*`, `hermes-4-405b`/`hermes-4-70b`).

## [Não lançado] — correção pós-instalação real (13/08/2026)

### Corrigido

- **O roteamento padrão quebrava no primeiro boot de quem não tem OMP.** Sete das
  dez rotas apontavam para o OMP como primário, com fallback em
  `qwen2.5:7b-instruct` (uma tag que o `ollama pull qwen2.5:7b` não cria) ou em
  OpenRouter (que exige chave). Numa máquina com só o Ollama no ar — exatamente o
  que a instalação pede — primário e fallback falhavam juntos, e o vídeo terminava
  o pipeline sem resumo, sem capítulos, sem tags e sem chat. Agora o padrão usa só
  Ollama com `qwen2.5:7b`, que é o mínimo já garantido pela instalação; OMP,
  DeepSeek, OpenRouter e Gemini continuam disponíveis, mas como escolha explícita
  em *Conexões de IA* em vez de pressuposto silencioso.
- **`make doctor` não avisava sobre o modelo de embeddings faltando.** Sem
  `nomic-embed-text` no Ollama, a indexação não quebra (o `step_index` captura a
  falha e segue), mas a metade semântica da busca híbrida some sem nenhum aviso —
  o usuário só descobriria comparando resultados. O diagnóstico agora verifica se
  o modelo está presente e mostra o `ollama pull` exato quando não está.

- **`make doctor` reportava `faster-whisper`/`ctranslate2` como ausentes mesmo
  depois de instalados.** O script testava o `python3` do sistema, não o venv
  do backend (`backend/.venv`), que é onde `pip install faster-whisper`
  realmente instala os pacotes — então o diagnóstico dava falso negativo
  mesmo com tudo certo. `scripts/doctor.sh` agora resolve o caminho do venv a
  partir da raiz do repo (funciona independente de onde o script é chamado) e
  usa esse Python nas duas checagens. Isso é só o diagnóstico: o `make dev`
  real já usava o Python certo o tempo todo, então quem bateu nesse aviso não
  estava bloqueado — só recebendo uma informação errada.

## [Não lançado] — revisão pós-entrega inicial (13/08/2026)

### Corrigido

- **Transcrição travava a API inteira.** `faster-whisper` é bloqueante e podia levar
  minutos; como o worker roda embutido no mesmo processo da API por padrão
  (`make dev`), o event loop inteiro ficava preso durante a transcrição —
  nenhuma requisição HTTP era atendida e o SSE de progresso parava de vez,
  exatamente a funcionalidade que o produto promete. `step_probe` (FFmpeg) e
  `step_transcribe` (Whisper) agora rodam em `asyncio.to_thread`, isolados do
  event loop. Em produção (`deploy/*.service`) isso já não acontecia, porque lá
  a API e o worker são processos systemd separados — mas o modo de
  desenvolvimento padrão precisava do mesmo cuidado.
- **`watch_status` era sobrescrito por engano.** Qualquer `PATCH /videos/{id}`
  sem relação com o player — favoritar, editar nota, renomear — recalculava o
  status de leitura a partir de `watched_seconds` já salvo e podia apagar
  silenciosamente um "revisitar" que o usuário tinha acabado de escolher. A
  lógica automática agora só roda quando a própria requisição reporta
  `watched_seconds`, e nunca por cima de um `watch_status` explícito na mesma
  chamada. Adicionado teste de regressão para os dois comportamentos.
- **Trocar de biblioteca pela sidebar não fazia nada** se você já estivesse em
  `/biblioteca`. O estado inicial só lia `?lib=` uma vez, na primeira montagem;
  navegações seguintes (mesma rota, query diferente) não disparavam nada. Agora
  um efeito observa o parâmetro da URL e sincroniza o estado sempre que muda.

### Adicionado

- Seletor de status de leitura (não visto / em andamento / concluído /
  revisitar) na página do vídeo — antes esse campo existia no modelo de dados e
  era documentado no README, mas não tinha nenhum controle na interface para
  defini-lo manualmente.
- `docs/INSTALACAO_UBUNTU.md`: guia completo para a topologia "tudo roda no
  servidor Ubuntu, acesso pelo navegador de outra máquina" — serviços systemd,
  nginx como única porta exposta, transferência de vídeos, backup do que
  importa, tabela de problemas comuns.
- `deploy/cloudsena-web.service`: faltava o serviço systemd do frontend (só
  existiam os da API e do worker).
- `LICENSE`, `CHANGELOG.md`.

### Alterado

- `deploy/nginx.conf` reescrito para a topologia local-only (API e frontend
  escutando só em `127.0.0.1`, nginx como único processo exposto na rede) — a
  versão anterior sugeria proteger a API com token, mas o proxy do próprio
  frontend não envia esse header, então ativá-lo trancava a interface.
- Removida chamada `fetch()` direta em `app/fila/page.tsx` que contornava o
  cliente de API tipado; agora usa `api.requeueStale()`.

### Verificado nesta rodada

- 13 testes de fumaça do backend (2 novos, cobrindo a regressão do
  `watch_status`).
- `tsc --noEmit` e `next build` limpos no frontend.
- Pipeline ponta a ponta reexecutado com `step_probe` e `step_transcribe`
  chamados via `asyncio.to_thread`, confirmando que o resultado não muda com o
  isolamento de thread.
- Página do vídeo renderizada em navegador headless com o seletor de status
  novo, sem erros de console além de um 404 de thumbnail esperado (vídeo de
  teste sintético).

## Fases 0–2 — entrega inicial

Ver `docs/ROADMAP.md` para o que foi entregue na primeira versão (scanner
local, pipeline retomável, busca híbrida, RAG com citações, painel de
providers com roteamento por tarefa, interface completa).
