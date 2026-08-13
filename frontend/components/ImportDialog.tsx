"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cx, formatBytes } from "@/lib/format";
import type { FolderPreview, Library } from "@/lib/types";
import { ErrorNote, Modal, Spinner, Toggle } from "./ui";

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
  const [path, setPath] = useState("");
  const [preview, setPreview] = useState<FolderPreview | null>(null);
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

  useEffect(() => {
    if (!path.trim()) {
      setPreview(null);
      return;
    }
    const timer = setTimeout(async () => {
      setChecking(true);
      setError("");
      try {
        setPreview(await api.previewFolder(path.trim()));
      } catch (e: any) {
        setError(e.message);
      } finally {
        setChecking(false);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [path]);

  const submit = async () => {
    if (!libraryId || !preview?.exists) return;
    setSaving(true);
    setError("");
    try {
      await api.createSource({
        library_id: libraryId,
        source_type: "local_folder",
        root_path: path.trim(),
        title: path.trim().split("/").filter(Boolean).pop() || "Pasta",
        scan_now: autoProcess,
      });
      onDone?.();
      onClose();
      setPath("");
      setPreview(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Importar cursos de uma pasta" wide>
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

        {checking && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner /> Verificando pasta…
          </div>
        )}

        {preview && !checking && (
          <div
            className={cx(
              "rounded-xl border p-4",
              preview.exists
                ? "border-signal-lime/25 bg-signal-lime/[.05]"
                : "border-signal-rose/25 bg-signal-rose/[.05]",
            )}
          >
            {preview.exists ? (
              <>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="font-semibold text-signal-lime">
                    {preview.count} vídeo(s) encontrados
                  </span>
                  {preview.total_bytes ? (
                    <span className="text-slate-400">{formatBytes(preview.total_bytes)}</span>
                  ) : null}
                  <span className="text-slate-400">
                    {preview.courses.length} curso(s) detectados
                  </span>
                </div>

                {preview.courses.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {preview.courses.slice(0, 12).map((course) => (
                      <span key={course} className="chip">
                        {course}
                      </span>
                    ))}
                  </div>
                )}

                {preview.files.length > 0 && (
                  <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto scroll-thin text-[12px] text-slate-400">
                    {preview.files.slice(0, 30).map((file) => (
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
          <button
            onClick={submit}
            disabled={!preview?.exists || saving || !libraryId}
            className="btn-primary"
          >
            {saving && <Spinner />}
            Importar {preview?.exists ? `${preview.count} vídeo(s)` : ""}
          </button>
        </div>
      </div>
    </Modal>
  );
}
