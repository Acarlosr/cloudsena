# CloudSena — caminho comercial

Este documento existe para que decisões técnicas de hoje não fechem portas comerciais amanhã.

---

## Posicionamento

> **Transforme sua biblioteca de vídeos em um segundo cérebro pesquisável.**

O concorrente não é o YouTube. É o caderno de anotações que ninguém relê e a pasta de cursos que
ninguém termina. O produto vende **recuperação**: achar em 30 segundos o que levaria 40 minutos de
rebobinar aula.

### O que diferencia

1. **Resposta com fonte e minuto.** Não é um chatbot que resume — é um índice que prova.
2. **Roda local de verdade.** Cursos pagos, material interno e gravações de reunião não precisam
   subir para lugar nenhum.
3. **Motor trocável.** O cliente usa a própria chave, ou nenhuma. Isso derruba a objeção de custo
   recorrente e a de compliance ao mesmo tempo.

---

## Produtos possíveis com este mesmo código

### 1. Aplicativo local premium — licença única ou anual
Público: profissionais com cursos comprados, advogados, médicos, traders, devs.
Argumento: privacidade + pagamento único. Custo marginal de IA é do próprio cliente.
Falta construir: instalador, licenciamento offline, auto-update.

### 2. Serviço em nuvem — assinatura mensal
Público: quem não quer instalar nada.
Argumento: sincronizar entre dispositivos, processar sem ocupar o computador.
Falta construir: contas, billing, storage de objetos, filas distribuídas, cotas.

### 3. Equipes / empresas — por usuário ou por hora processada
Público: treinamento corporativo, onboarding, documentação interna em vídeo, suporte.
Argumento: "o conhecimento da empresa está em 300 h de gravação que ninguém consegue consultar."
Falta construir: organizações, permissões por biblioteca, SSO, painel de uso, auditoria.

**Esse é o de maior valor por contrato** — e o que mais depende de ter começado com a arquitetura certa.

---

## Estrutura de planos (esqueleto)

| Plano | Para quem | Limites |
|---|---|---|
| Free | avaliação | 1 biblioteca, poucas horas processadas, só motores locais |
| Personal | uso individual | bibliotecas ilimitadas, IA, sincronização |
| Pro | uso intenso | análise visual, modelos avançados, comparação entre cursos |
| Team | empresas | usuários, permissões, bibliotecas compartilhadas, painel |
| Private | compliance | instalação no servidor do cliente, licença anual |

**Não defina preço antes de medir.** O `UsageLog` já grava tokens, custo e latência por tarefa e por
vídeo. Depois de processar ~50 h reais de curso você terá o custo por hora de vídeo em cada rota
(local vs. API) — é esse número que define a margem e, portanto, o preço.

---

## O que já está pronto para a versão comercial

- `Library.owner_id` e `Conversation.user_id` existem: multi-tenant não exige migração destrutiva.
- `UsageLog` mede custo por provider, modelo, tarefa e vídeo — base de cotas e de billing por uso.
- Modos de privacidade por biblioteca: o mesmo binário atende o cliente paranóico e o pragmático.
- Providers plugáveis: dá para vender "traga sua própria chave" (margem alta, sem risco de custo).
- Fila retomável e reprocessamento individual: requisito para suporte a cliente pagante.
- API documentada em OpenAPI: integração com LMS e intranet sem trabalho extra.

## O que falta, em ordem de dependência

1. **Autenticação** (usuários, sessões, hash de senha) — bloqueia tudo o mais.
2. **Organizações e permissões** por biblioteca.
3. **Cotas e limites** por plano, lendo do `UsageLog`.
4. **Billing** (Stripe) + webhooks de assinatura.
5. **Instalador** (Docker Compose para servidor; AppImage/DMG para desktop).
6. **Telemetria opcional** e consentida, para saber onde o produto trava.
7. **Avaliação automática de respostas** — dataset de perguntas com resposta conhecida, rodado a cada
   troca de modelo. É o que impede uma "melhoria" de piorar a qualidade sem ninguém perceber.

---

## Métricas que importam

| Métrica | Meta inicial |
|---|---|
| Tempo até a primeira resposta útil (instalação → pergunta respondida) | < 30 min |
| Tempo de transcrição por hora de vídeo (RTX 3060 Ti, large-v3) | medir e publicar |
| Custo de IA por hora de vídeo processada | medir por rota |
| Taxa de respostas ancoradas (com citação real) | > 90% |
| Taxa de "não encontrei" indevidos | < 5% |
| Vídeos que falham no pipeline | < 2% |

As três últimas são de **qualidade** e definem se o produto é vendável. As duas primeiras definem se
ele é viável.

---

## Riscos conhecidos

- **API do YouTube:** playlists especiais (Assistir mais tarde) não são acessíveis oficialmente. A
  Fase 3 deve priorizar playlists normais e entrada manual por URL, e comunicar o limite com clareza.
- **Direitos autorais:** processar curso pago é uso pessoal; **redistribuir** transcrição não é. A
  versão em nuvem precisa de termos claros e da decisão explícita de não compartilhar transcrições
  entre contas.
- **Custo de suporte:** transcrição local em máquina do cliente gera chamados de CUDA/driver. O
  `make doctor` existe justamente para transformar isso em autoatendimento.
- **Dependência de um provider:** mitigada pelo roteamento com fallback — nenhum plano deve depender
  de um único fornecedor de IA.
