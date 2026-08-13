"""Catálogo de providers de IA suportados pelo CloudSena.

Cada entrada descreve *como conectar*. As credenciais ficam no banco,
criptografadas, e nunca são expostas ao frontend.

kind:
  openai_compatible -> usa /chat/completions no padrão OpenAI
  ollama            -> API nativa do Ollama (local)
  gemini            -> Google Generative Language API
  anthropic         -> Anthropic Messages API
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    slug: str
    label: str
    kind: str
    base_url: str
    docs_url: str = ""
    api_key_url: str = ""
    requires_key: bool = True
    is_local: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    supports_model_listing: bool = True
    default_model: str = ""
    suggested_models: list[str] = field(default_factory=list)
    extra_headers: dict[str, str] = field(default_factory=dict)
    notes: str = ""


CATALOG: list[ProviderSpec] = [
    # ---------------- Locais ----------------
    ProviderSpec(
        slug="ollama",
        label="Ollama (local)",
        kind="ollama",
        base_url="http://localhost:11434",
        docs_url="https://ollama.com",
        requires_key=False,
        is_local=True,
        supports_vision=True,
        supports_embeddings=True,
        default_model="qwen2.5:7b-instruct",
        suggested_models=[
            "qwen2.5:7b-instruct",
            "llama3.1:8b",
            "gemma2:9b",
            "mistral-nemo",
            "llava:13b",
            "nomic-embed-text",
        ],
        notes="Motor local padrão. Ideal para o modo Privado — nada sai da máquina.",
    ),
    ProviderSpec(
        slug="omp",
        label="Oh-my-pi / OMP (local)",
        kind="openai_compatible",
        base_url="http://localhost:8080/v1",
        requires_key=False,
        is_local=True,
        default_model="deepseek/deepseek-v4-flash-0731",
        suggested_models=[
            "deepseek/deepseek-v4-pro",
            "nous/deepseek/deepseek-v4-flash-0731",
            "google/gemini-3.1-flash-lite",
            "google/gemini-2.5-flash-lite",
        ],
        notes="Gateway OMP já rodando na máquina, expondo DeepSeek e Gemini via padrão OpenAI.",
    ),
    ProviderSpec(
        slug="lmstudio",
        label="LM Studio (local)",
        kind="openai_compatible",
        base_url="http://localhost:1234/v1",
        requires_key=False,
        is_local=True,
        default_model="local-model",
        notes="Servidor local do LM Studio no padrão OpenAI.",
    ),
    ProviderSpec(
        slug="vllm",
        label="vLLM / TGI (self-hosted)",
        kind="openai_compatible",
        base_url="http://localhost:8000/v1",
        requires_key=False,
        is_local=True,
        default_model="",
        notes="Qualquer servidor OpenAI-compatible self-hosted.",
    ),
    ProviderSpec(
        slug="llamacpp",
        label="llama.cpp server (local)",
        kind="openai_compatible",
        base_url="http://localhost:8081/v1",
        requires_key=False,
        is_local=True,
        default_model="",
    ),

    # ---------------- Agregadores ----------------
    ProviderSpec(
        slug="openrouter",
        label="OpenRouter",
        kind="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        docs_url="https://openrouter.ai/docs",
        api_key_url="https://openrouter.ai/keys",
        supports_vision=True,
        default_model="deepseek/deepseek-chat",
        suggested_models=[
            "deepseek/deepseek-chat",
            "deepseek/deepseek-r1",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
            "nousresearch/hermes-3-llama-3.1-405b",
        ],
        extra_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "CloudSena",
        },
        notes="Acesso a centenas de modelos com uma única chave. Ótimo para fallback.",
    ),

    # ---------------- Diretos ----------------
    ProviderSpec(
        slug="deepseek",
        label="DeepSeek",
        kind="openai_compatible",
        base_url="https://api.deepseek.com/v1",
        docs_url="https://api-docs.deepseek.com",
        api_key_url="https://platform.deepseek.com/api_keys",
        default_model="deepseek-chat",
        suggested_models=["deepseek-chat", "deepseek-reasoner"],
        notes="Custo baixo por token — recomendado para resumos em lote.",
    ),
    ProviderSpec(
        slug="nous",
        label="Nous Research (Portal)",
        kind="openai_compatible",
        base_url="https://inference-api.nousresearch.com/v1",
        docs_url="https://portal.nousresearch.com",
        api_key_url="https://portal.nousresearch.com",
        default_model="Hermes-4-70B",
        suggested_models=["Hermes-4-70B", "Hermes-4-405B", "DeepHermes-3-Llama-3-8B-Preview"],
    ),
    ProviderSpec(
        slug="openai",
        label="OpenAI",
        kind="openai_compatible",
        base_url="https://api.openai.com/v1",
        api_key_url="https://platform.openai.com/api-keys",
        supports_vision=True,
        supports_embeddings=True,
        default_model="gpt-4o-mini",
        suggested_models=["gpt-4o-mini", "gpt-4o", "o4-mini", "text-embedding-3-small"],
    ),
    ProviderSpec(
        slug="anthropic",
        label="Anthropic",
        kind="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_url="https://console.anthropic.com/settings/keys",
        supports_vision=True,
        supports_model_listing=True,
        default_model="claude-sonnet-4-20250514",
        suggested_models=["claude-sonnet-4-20250514", "claude-3-5-haiku-latest"],
    ),
    ProviderSpec(
        slug="gemini",
        label="Google Gemini",
        kind="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_url="https://aistudio.google.com/apikey",
        supports_vision=True,
        supports_embeddings=True,
        default_model="gemini-2.5-flash",
        suggested_models=["gemini-2.5-flash", "gemini-2.5-pro", "text-embedding-004"],
        notes="Melhor opção para análise visual de slides e código na tela.",
    ),
    ProviderSpec(
        slug="groq",
        label="Groq",
        kind="openai_compatible",
        base_url="https://api.groq.com/openai/v1",
        api_key_url="https://console.groq.com/keys",
        default_model="llama-3.3-70b-versatile",
        suggested_models=["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        notes="Latência muito baixa — bom para tarefas em lote.",
    ),
    ProviderSpec(
        slug="together",
        label="Together AI",
        kind="openai_compatible",
        base_url="https://api.together.xyz/v1",
        api_key_url="https://api.together.ai/settings/api-keys",
        supports_embeddings=True,
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
    ),
    ProviderSpec(
        slug="mistral",
        label="Mistral AI",
        kind="openai_compatible",
        base_url="https://api.mistral.ai/v1",
        api_key_url="https://console.mistral.ai/api-keys",
        supports_embeddings=True,
        default_model="mistral-large-latest",
    ),
    ProviderSpec(
        slug="fireworks",
        label="Fireworks AI",
        kind="openai_compatible",
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_url="https://fireworks.ai/account/api-keys",
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
    ),
    ProviderSpec(
        slug="xai",
        label="xAI (Grok)",
        kind="openai_compatible",
        base_url="https://api.x.ai/v1",
        api_key_url="https://console.x.ai",
        supports_vision=True,
        default_model="grok-4",
    ),
    ProviderSpec(
        slug="cerebras",
        label="Cerebras",
        kind="openai_compatible",
        base_url="https://api.cerebras.ai/v1",
        api_key_url="https://cloud.cerebras.ai",
        default_model="llama-3.3-70b",
    ),
    ProviderSpec(
        slug="perplexity",
        label="Perplexity",
        kind="openai_compatible",
        base_url="https://api.perplexity.ai",
        api_key_url="https://www.perplexity.ai/settings/api",
        supports_model_listing=False,
        default_model="sonar-pro",
    ),
    ProviderSpec(
        slug="custom",
        label="Endpoint personalizado",
        kind="openai_compatible",
        base_url="",
        requires_key=False,
        supports_model_listing=True,
        notes="Qualquer API compatível com OpenAI. Informe base_url e chave.",
    ),
]

BY_SLUG: dict[str, ProviderSpec] = {p.slug: p for p in CATALOG}


def spec_for(slug: str) -> ProviderSpec | None:
    return BY_SLUG.get(slug)


# Preços de referência (USD por 1M tokens) para estimativa de custo na UI.
# Apenas orientativo — ajuste conforme o seu contrato.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "deepseek/deepseek-chat": (0.27, 1.10),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price = PRICE_TABLE.get(model)
    if not price:
        return 0.0
    pin, pout = price
    return (tokens_in / 1_000_000) * pin + (tokens_out / 1_000_000) * pout
