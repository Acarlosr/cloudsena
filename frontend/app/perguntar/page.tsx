"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import AnswerBlock from "@/components/AnswerBlock";
import { Badge, EmptyState, ErrorNote, Panel, Spinner, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { cx, formatDuration } from "@/lib/format";
import type { AnswerResponse, Library, SearchHit } from "@/lib/types";

type Entry = { question: string; answer: AnswerResponse };

const EXAMPLES = [
  "Onde foi explicado o risco de impermanent loss?",
  "Resuma o que foi ensinado sobre gestão de risco",
  "Em qual aula aparece a configuração do webhook?",
  "Quais ferramentas foram recomendadas no curso?",
];

export default function AskPage() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryId, setLibraryId] = useState<number | undefined>();
  const [courses, setCourses] = useState<{ course: string; videos: number }[]>([]);
  const [course, setCourse] = useState("");
  const [question, setQuestion] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deep, setDeep] = useState(false);
  const [mode, setMode] = useState<"ask" | "search">("ask");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.libraries().then((libs) => {
      setLibraries(libs);
      setLibraryId((cur) => cur ?? libs[0]?.id);
    });
  }, []);

  useEffect(() => {
    if (libraryId) api.courses(libraryId).then(setCourses).catch(() => setCourses([]));
  }, [libraryId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length, loading]);

  const submit = async (text?: string) => {
    const q = (text ?? question).trim();
    if (!q) return;
    setLoading(true);
    setError("");
    setQuestion("");

    try {
      if (mode === "search") {
        const result = await api.search({ query: q, library_id: libraryId, course });
        setHits(result.results);
      } else {
        const answer = await api.ask({
          question: q,
          library_id: libraryId,
          course: course || undefined,
          conversation_id: conversationId,
          deep_reasoning: deep,
        });
        setConversationId(answer.conversation_id);
        setEntries((prev) => [...prev, { question: q, answer }]);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setEntries([]);
    setHits([]);
    setConversationId(undefined);
    setError("");
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Perguntar</div>
          <h1 className="text-3xl font-semibold">Converse com sua biblioteca</h1>
          <p className="mt-1.5 text-sm text-slate-400">
            As respostas vêm apenas dos seus vídeos, sempre com o trecho e o minuto de origem.
          </p>
        </div>
        {(entries.length > 0 || hits.length > 0) && (
          <button onClick={reset} className="btn-ghost">
            Nova conversa
          </button>
        )}
      </header>

      <Panel className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1 rounded-lg border border-white/[.07] bg-ink-850 p-1">
            {(["ask", "search"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cx(
                  "rounded-md px-3 py-1 text-xs transition",
                  mode === m ? "bg-accent/20 text-accent-soft" : "text-slate-400 hover:text-white",
                )}
              >
                {m === "ask" ? "✧ Resposta" : "⌕ Só trechos"}
              </button>
            ))}
          </div>

          <select
            value={libraryId ?? ""}
            onChange={(e) => {
              setLibraryId(Number(e.target.value));
              setCourse("");
            }}
            className="text-[13px]"
          >
            {libraries.map((lib) => (
              <option key={lib.id} value={lib.id}>
                {lib.name}
              </option>
            ))}
          </select>

          <select
            value={course}
            onChange={(e) => setCourse(e.target.value)}
            className="text-[13px]"
          >
            <option value="">Todos os cursos</option>
            {courses.map((c) => (
              <option key={c.course} value={c.course}>
                {c.course} ({c.videos})
              </option>
            ))}
          </select>

          {mode === "ask" && (
            <label className="ml-auto flex items-center gap-2 text-xs text-slate-400">
              Raciocínio profundo
              <Toggle checked={deep} onChange={setDeep} />
            </label>
          )}
        </div>

        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
            placeholder={
              mode === "ask"
                ? "Onde foi explicado…?"
                : "Palavras que aparecem na aula…"
            }
            className="flex-1"
            autoFocus
          />
          <button onClick={() => submit()} disabled={loading || !question.trim()} className="btn-primary">
            {loading ? <Spinner /> : mode === "ask" ? "Perguntar" : "Buscar"}
          </button>
        </div>

        {deep && mode === "ask" && (
          <p className="text-[11px] text-slate-500">
            Usa o modelo configurado em <span className="text-slate-400">Perguntas complexas</span>{" "}
            — mais lento e mais caro, melhor para comparações entre aulas.
          </p>
        )}
      </Panel>

      <ErrorNote message={error} />

      {entries.length === 0 && hits.length === 0 && !loading && (
        <EmptyState
          icon="✧"
          title="Faça a primeira pergunta"
          description="O CloudSena procura nos trechos transcritos, seleciona os mais relevantes e responde citando cada fonte."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => submit(example)}
                  className="chip transition hover:border-accent/40 hover:text-accent-soft"
                >
                  {example}
                </button>
              ))}
            </div>
          }
        />
      )}

      {mode === "ask" &&
        entries.map((entry, index) => (
          <div key={index} className="space-y-3 animate-fade-up">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent/15 px-4 py-2.5 text-sm text-slate-100">
                {entry.question}
              </div>
            </div>
            <Panel className="p-5">
              <AnswerBlock answer={entry.answer} />
            </Panel>
          </div>
        ))}

      {mode === "search" && hits.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-slate-500">{hits.length} trecho(s) encontrados</div>
          {hits.map((hit) => (
            <Link
              key={hit.chunk_id}
              href={`/video/${hit.video_id}?t=${Math.floor(hit.start)}`}
              className="panel panel-hover flex gap-4 p-3"
            >
              <div className="relative h-16 w-28 shrink-0 overflow-hidden rounded-lg bg-ink-800">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={api.thumbUrl(hit.video_id)}
                  alt=""
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
                <span className="mono-num absolute bottom-1 right-1 rounded bg-black/80 px-1 text-[9px] text-white">
                  {formatDuration(hit.start)}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {hit.course && (
                    <span className="text-[10px] uppercase tracking-wide text-accent-soft/80">
                      {hit.course}
                    </span>
                  )}
                  {hit.chapter && <Badge>{hit.chapter}</Badge>}
                </div>
                <div className="mt-0.5 truncate text-sm font-medium text-slate-200">
                  {hit.video_title}
                </div>
                <p className="mt-1 line-clamp-2 text-[12.5px] leading-snug text-slate-500">
                  {hit.text}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}

      {loading && (
        <Panel className="flex items-center gap-3 p-5 text-sm text-slate-400">
          <Spinner className="text-accent" />
          {mode === "ask"
            ? "Recuperando trechos, reordenando por relevância e redigindo a resposta…"
            : "Buscando…"}
        </Panel>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
