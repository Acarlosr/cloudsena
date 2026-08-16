"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cx, formatBytes, formatDuration } from "@/lib/format";
import type { FolderPreview, Library, PlaylistPreview } from "@/lib/types";
import { ErrorNote, Modal, Spinner, Toggle } from "./ui";

type Mode = "local_folder" | "youtube";

export default function ImportDialog({
  open,
  onClose,
  onDone,
  defaultLibraryId,
}: {
  open: boolean;
  onClose: () => void;
  onDone?: () => void;
  defaultLibraryId?: number;
}) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryId, setLibraryId] = useState<number | undefined>(defaultLibraryId);
  const [mode, setMode] = useState<Mode>("local_folder");

  const [path, setPath] = useState("");
  const [folderPreview, setFolderPreview] = useState<FolderPreview | null>(null);

  const [playlistUrl, setPlaylistUrl] = useState("");
  const [playlistPreview, setPlaylistPreview] = useState<PlaylistPreview | null>(null);

  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoProcess, setAutoProcess] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    api.libraries().then((libs) => {
      setLibraries(libs);
      setLibraryId((cur) => cur ?? libs[0]?.id);
    });
  }, [open]);

  // Prévia da pasta local — debounced.
  useEffect(() => {
    if (mode !== "local_folder" || !path.trim()) {
      setFolderPreview(null);
      return;
    }
    const timer = setTimeout(async () => {
      setChecking(true);
      setError("");
      try {
        setFolderPreview(await api.previewFolder(path.trim()));
      } catch (e: any) {
        setError(e.message);
      } finally {
        setChecking(false);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [path, mode]);

  // Prévia da playlist do YouTube — debounced. Só metadados, nada é baixado.
  useEffect(() => {
    if (mode !== "youtube" || !playlistUrl.trim()) {
      setPlaylistPreview(null);
      return;
    }
    const timer = setTimeout(async () => {
      setChecking(true);
      setError("");
      try {
        const result = await api.previewPlaylist(playlistUrl.trim());
        setPlaylistPreview(result);
        if (!result.exists && result.error) setError(result.error);
      } catch (e: any) {
        setError(e.message);
      } finally {
        setChecking(false);
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [playlistUrl, mode]);

  const reset = () => {
    setPath("");
    setFolderPreview(null);
    setPlaylistUrl("");
    setPlaylistPreview(null);
  };

  const submit = async () => {
    if (!libraryId) return;
    setSaving(true);
    setError("");
    try {
      if (mode === "local_folder") {
        if (!folderPreview?.exists) return;
        await api.createSource({
          library_id: libraryId,
          source_type: "local_folder",
          root_path: path.trim(),
          title: path.trim().split("/").filter(Boolean).pop() || "Pasta",
          scan_now: autoProcess,
        });
      } else {
        if (!playlistPreview?.exists) return;
        await api.createSource({
          library_id: libraryId,
          source_type: "youtube",
          url: playlistUrl.trim(),
          title: playlistPreview.courses[0] || "Playlist do YouTube",
          scan_now: autoProcess,
        });
      }
      onDone?.();
      onClose();
      reset();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const canSubmit =
    !!libraryId &&
    !saving &&
    (mode === "local_folder" ? !!folderPreview?.exists : !!playlistPreview?.exists);

  return (
    <Modal open={open} onClose={onClose} title="Importar vídeos" wide>
      <div className="space-y-5">
        <div>
          <label className="label">Biblioteca de destino</label>
          <select
            value={libraryId ?? ""}
            onChange={(e) => setLibraryId(Number(e.target.value))}
            className="w-full"
          >
            {libraries.map((lib) => (
              <option key={lib.id} value={lib.id}>
                {lib.name} · {lib.privacy_mode}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-1 rounded-lg border border-white/[.07] bg-ink-850 p-1 w-fit">
          {(
            [
              { value: "local_folder", label: "Pasta local" },
              { value: "youtube", label: "Playlist do YouTube" },
            ] as { value: Mode; label: string }[]
          ).map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                setMode(opt.value);
                setError("");
              }}
              className={cx(
                "rounded-md px-3 py-1.5 text-xs transition",
                mode === opt.value
                  ? "bg-accent/20 text-accent-soft"
                  : "text-slate-400 hover:text-white",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {mode === "local_folder" ? (
          <div>
            <label className="label">Caminho da pasta no servidor</label>
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="/home/usuario/Cursos/Trading"
              className="w-full font-mono text-[13px]"
              autoFocus
            />
            <p className="mt-1.5 text-[11px] text-slate-500">
              O caminho é lido pelo backend. Os arquivos permanecem onde estão — o CloudSena nunca
              copia nem move seus vídeos.
            </p>
          </div>
        ) : (
          <div>
            <label className="label">URL da playlist</label>
            <input
              value={playlistUrl}
              onChange={(e) => setPlaylistUrl(e.target.value)}
              placeholder="https://www.youtube.com/playlist?list=..."
              className="w-full font-mono text-[13px]"
              autoFocus
            />
            <p className="mt-1.5 text-[11px] text-slate-500">
              Nada é baixado agora — só a lista de vídeos. Na transcrição, o CloudSena baixa
              apenas o áudio de cada vídeo (nunca o vídeo inteiro) e descarta depois. A reprodução
              usa o player do YouTube.
            </p>
          </div>
        )}

        {checking && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner /> {mode === "local_folder" ? "Verificando pasta…" : "Lendo playlist…"}
          </div>
        )}

        {mode === "local_folder" && folderPreview && !checking && (
          <div
            className={cx(
              "rounded-xl border p-4",
              folderPreview.exists
                ? "border-signal-lime/25 bg-signal-lime/[.05]"
                : "border-signal-rose/25 bg-signal-rose/[.05]",
            )}
          >
            {folderPreview.exists ? (
              <>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="font-semibold text-signal-lime">
                    {folderPreview.count} vídeo(s) encontrados
                  </span>
                  {folderPreview.total_bytes ? (
                    <span className="text-slate-400">{formatBytes(folderPreview.total_bytes)}</span>
                  ) : null}
                  <span className="text-slate-400">
                    {folderPreview.courses.length} curso(s) detectados
                  </span>
                </div>

                {folderPreview.courses.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {folderPreview.courses.slice(0, 12).map((course) => (
                      <span key={course} className="chip">
                        {course}
                      </span>
                    ))}
                  </div>
                )}

                {folderPreview.files.length > 0 && (
                  <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto scroll-thin text-[12px] text-slate-400">
                    {folderPreview.files.slice(0, 30).map((file) => (
                      <li key={file.path} className="flex justify-between gap-3">
                        <span className="truncate">{file.title}</span>
                        <span className="mono-num shrink-0 text-slate-600">
                          {formatBytes(file.size)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-sm text-signal-rose">
                Pasta não encontrada. Confira o caminho exato no servidor onde o backend roda.
              </p>
            )}
          </div>
        )}

        {mode === "youtube" && playlistPreview && !checking && playlistPreview.exists && (
          <div className="rounded-xl border border-signal-lime/25 bg-signal-lime/[.05] p-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="font-semibold text-signal-lime">
                {playlistPreview.count} vídeo(s) na playlist
              </span>
              <span className="text-slate-400">{playlistPreview.courses[0]}</span>
            </div>

            {playlistPreview.files.length > 0 && (
              <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto scroll-thin text-[12px] text-slate-400">
                {playlistPreview.files.slice(0, 30).map((file) => (
                  <li key={file.path} className="flex justify-between gap-3">
                    <span className="truncate">{file.title}</span>
                    {file.duration > 0 && (
                      <span className="mono-num shrink-0 text-slate-600">
                        {formatDuration(file.duration)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex items-center justify-between rounded-xl border border-white/[.07] bg-white/[.02] px-4 py-3">
          <div>
            <div className="text-sm text-slate-200">Processar automaticamente</div>
            <p className="text-[11px] text-slate-500">
              Enfileira transcrição, resumo e indexação assim que os vídeos forem descobertos.
            </p>
          </div>
          <Toggle checked={autoProcess} onChange={setAutoProcess} />
        </div>

        <ErrorNote message={error} />

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="btn-ghost">
            Cancelar
          </button>
          <button onClick={submit} disabled={!canSubmit} className="btn-primary">
            {saving && <Spinner />}
            Importar{" "}
            {mode === "local_folder"
              ? folderPreview?.exists
                ? `${folderPreview.count} vídeo(s)`
                : ""
              : playlistPreview?.exists
                ? `${playlistPreview.count} vídeo(s)`
                : ""}
          </button>
        </div>
      </div>
    </Modal>
  );
}
