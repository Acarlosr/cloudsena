"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, ErrorNote, Modal, Panel, SectionTitle, Spinner, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { cx, formatRelative } from "@/lib/format";
import type { Provider, RoutingRule } from "@/lib/types";

export default function ConnectionsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [routes, setRoutes] = useState<RoutingRule[]>([]);
  const [editing, setEditing] = useState<Provider | null>(null);
  const [testing, setTesting] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [p, r] = await Promise.all([api.providers(), api.routes()]);
      setProviders(p);
      setRoutes(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const test = async (slug: string) => {
    setTesting(slug);
    try {
      await api.testProvider(slug);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTesting("");
    }
  };

  const toggle = async (provider: Provider, enabled: boolean) => {
    try {
      await api.updateProvider(provider.slug, { enabled });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const locals = providers.filter((p) => p.is_local);
  const remotes = providers.filter((p) => !p.is_local);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Conexões de IA</div>
          <h1 className="text-3xl font-semibold">Motores e roteamento</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-slate-400">
            Ligue os motores que quiser usar e escolha qual modelo atende cada tarefa. As chaves
            ficam criptografadas no backend e nunca chegam ao navegador.
          </p>
        </div>
        <button
          onClick={async () => {
            setTesting("all");
            await api.testAllProviders().catch(() => {});
            await load();
            setTesting("");
          }}
          className="btn-ghost"
        >
          {testing === "all" ? <Spinner /> : "⌁"} Testar todos
        </button>
      </header>

      <ErrorNote message={error} />

      <section>
        <SectionTitle
          title="Motores locais"
          subtitle="Rodam na sua máquina. Custo zero por token e nenhum dado sai do computador."
        />
        <div className="grid gap-3 md:grid-cols-2">
          {loading
            ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="skeleton h-36" />)
            : locals.map((provider) => (
                <ProviderCard
                  key={provider.slug}
                  provider={provider}
                  testing={testing === provider.slug}
                  onTest={() => test(provider.slug)}
                  onToggle={(v) => toggle(provider, v)}
                  onEdit={() => setEditing(provider)}
                />
              ))}
        </div>
      </section>

      <section>
        <SectionTitle
          title="APIs externas"
          subtitle="Adicione a chave para habilitar. Modelos mais fortes para resumo em lote e perguntas complexas."
        />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {remotes.map((provider) => (
            <ProviderCard
              key={provider.slug}
              provider={provider}
              testing={testing === provider.slug}
              onTest={() => test(provider.slug)}
              onToggle={(v) => toggle(provider, v)}
              onEdit={() => setEditing(provider)}
            />
          ))}
        </div>
      </section>

      <section>
        <SectionTitle
          title="Roteamento por tarefa"
          subtitle="Cada etapa do pipeline pode usar um motor diferente — com fallback automático se o principal falhar."
        />
        <Panel className="divide-y divide-white/[.05]">
          {routes.map((rule) => (
            <RouteRow
              key={rule.task}
              rule={rule}
              providers={providers.filter((p) => p.enabled)}
              onSave={async (patch) => {
                await api.updateRoute(rule.task, patch);
                await load();
              }}
            />
          ))}
        </Panel>
      </section>

      <ProviderDialog
        provider={editing}
        onClose={() => setEditing(null)}
        onSaved={async () => {
          setEditing(null);
          await load();
        }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function ProviderCard({
  provider,
  testing,
  onTest,
  onToggle,
  onEdit,
}: {
  provider: Provider;
  testing: boolean;
  onTest: () => void;
  onToggle: (v: boolean) => void;
  onEdit: () => void;
}) {
  const tone =
    provider.status === "ok"
      ? "border-signal-lime/25 bg-signal-lime/10 text-signal-lime"
      : provider.status === "error"
        ? "border-signal-rose/25 bg-signal-rose/10 text-signal-rose"
        : "border-white/10 bg-white/[.04] text-slate-400";

  const blocked = provider.requires_key && !provider.has_key;

  return (
    <Panel className={cx("p-4", provider.enabled && "border-accent/20")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-[15px] font-semibold text-slate-100">{provider.label}</h3>
            {provider.is_local && <Badge dot="bg-signal-cyan">local</Badge>}
          </div>
          <p className="mt-1 font-mono text-[10.5px] text-slate-500 truncate">
            {provider.base_url || "—"}
          </p>
        </div>
        <Toggle
          checked={provider.enabled}
          onChange={onToggle}
          disabled={blocked}
        />
      </div>

      {provider.notes && (
        <p className="mt-2.5 line-clamp-2 text-[12px] leading-snug text-slate-500">
          {provider.notes}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Badge className={tone}>
          {provider.status === "ok" ? "conectado" : provider.status === "error" ? "erro" : "não testado"}
        </Badge>
        {provider.requires_key && (
          <Badge>{provider.has_key ? `chave ${provider.key_masked}` : "sem chave"}</Badge>
        )}
        {provider.supports_vision && <Badge>visão</Badge>}
        {provider.supports_embeddings && <Badge>embeddings</Badge>}
      </div>

      {provider.status_message && (
        <p
          className={cx(
            "mt-2 line-clamp-2 text-[11px]",
            provider.status === "error" ? "text-signal-rose/80" : "text-slate-500",
          )}
        >
          {provider.status_message}
        </p>
      )}

      <div className="mt-3.5 flex items-center gap-2">
        <button onClick={onEdit} className="btn-ghost flex-1 text-xs">
          Configurar
        </button>
        <button onClick={onTest} disabled={testing} className="btn-ghost text-xs">
          {testing ? <Spinner className="h-3.5 w-3.5" /> : "Testar"}
        </button>
      </div>

      {provider.last_checked_at && (
        <p className="mt-2 text-[10px] text-slate-600">
          testado {formatRelative(provider.last_checked_at)}
        </p>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
function ProviderDialog({
  provider,
  onClose,
  onSaved,
}: {
  provider: Provider | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<{ id: string; label: string }[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!provider) return;
    setBaseUrl(provider.base_url);
    setModel(provider.default_model);
    setApiKey("");
    setError("");
    setModels(provider.suggested_models.map((id) => ({ id, label: id })));
  }, [provider]);

  if (!provider) return null;

  const fetchModels = async () => {
    setLoadingModels(true);
    try {
      const result = await api.providerModels(provider.slug, true);
      setModels(result.models);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingModels(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const patch: Record<string, unknown> = { base_url: baseUrl, default_model: model };
      if (apiKey) patch.api_key = apiKey;
      await api.updateProvider(provider.slug, patch);
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={provider.label} wide>
      <div className="space-y-4">
        <div>
          <label className="label">Endpoint (base URL)</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className="w-full font-mono text-[13px]"
            placeholder="https://api.exemplo.com/v1"
          />
        </div>

        {provider.requires_key && (
          <div>
            <label className="label">Chave de API</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={provider.has_key ? `Salva: ${provider.key_masked}` : "sk-…"}
              className="w-full font-mono text-[13px]"
              autoComplete="off"
            />
            <div className="mt-1.5 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">
                Criptografada no banco. Nunca é devolvida ao navegador.
              </span>
              {provider.api_key_url && (
                <a
                  href={provider.api_key_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent-soft hover:underline"
                >
                  obter chave ↗
                </a>
              )}
            </div>
          </div>
        )}

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="label mb-0">Modelo padrão</label>
            <button onClick={fetchModels} className="text-[11px] text-accent-soft hover:underline">
              {loadingModels ? "carregando…" : "buscar modelos disponíveis"}
            </button>
          </div>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            list={`models-${provider.slug}`}
            className="w-full font-mono text-[13px]"
            placeholder="nome-do-modelo"
          />
          <datalist id={`models-${provider.slug}`}>
            {models.map((m) => (
              <option key={m.id} value={m.id} />
            ))}
          </datalist>
          {models.length > 0 && (
            <div className="mt-2 flex max-h-28 flex-wrap gap-1.5 overflow-y-auto scroll-thin">
              {models.slice(0, 40).map((m) => (
                <button
                  key={m.id}
                  onClick={() => setModel(m.id)}
                  className={cx(
                    "chip transition hover:border-accent/40",
                    model === m.id && "border-accent/40 bg-accent/15 text-accent-soft",
                  )}
                >
                  {m.id}
                </button>
              ))}
            </div>
          )}
        </div>

        <ErrorNote message={error} />

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="btn-ghost">
            Cancelar
          </button>
          <button onClick={save} disabled={saving} className="btn-primary">
            {saving && <Spinner />} Salvar
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
function RouteRow({
  rule,
  providers,
  onSave,
}: {
  rule: RoutingRule;
  providers: Provider[];
  onSave: (patch: Record<string, unknown>) => Promise<void>;
}) {
  const [slug, setSlug] = useState(rule.provider_slug);
  const [model, setModel] = useState(rule.model);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSlug(rule.provider_slug);
    setModel(rule.model);
    setDirty(false);
  }, [rule]);

  const current = providers.find((p) => p.slug === slug);

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="min-w-[190px] flex-1">
        <div className="text-sm text-slate-200">{rule.label || rule.task}</div>
        <div className="font-mono text-[10px] text-slate-600">{rule.task}</div>
      </div>

      <select
        value={slug}
        onChange={(e) => {
          setSlug(e.target.value);
          setDirty(true);
        }}
        className="min-w-[150px] text-[13px]"
      >
        <option value="">— desativado —</option>
        {providers.map((p) => (
          <option key={p.slug} value={p.slug}>
            {p.label}
          </option>
        ))}
      </select>

      <input
        value={model}
        onChange={(e) => {
          setModel(e.target.value);
          setDirty(true);
        }}
        list={`route-models-${rule.task}`}
        placeholder={current?.default_model || "modelo"}
        className="min-w-[200px] flex-1 font-mono text-[12px]"
      />
      <datalist id={`route-models-${rule.task}`}>
        {(current?.suggested_models || []).map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>

      {rule.fallback_provider_slug && (
        <span className="hidden text-[11px] text-slate-600 xl:inline">
          fallback: {rule.fallback_provider_slug}
        </span>
      )}

      <button
        onClick={async () => {
          setSaving(true);
          await onSave({ provider_slug: slug, model });
          setSaving(false);
          setDirty(false);
        }}
        disabled={!dirty || saving}
        className={cx("btn text-xs", dirty ? "btn-primary" : "btn-ghost")}
      >
        {saving ? <Spinner className="h-3.5 w-3.5" /> : "Salvar"}
      </button>
    </div>
  );
}
