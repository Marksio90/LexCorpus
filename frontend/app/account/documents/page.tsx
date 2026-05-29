"use client";

import { useState, useEffect, useRef } from "react";
import { useSession } from "next-auth/react";

interface PrivateDoc {
  id:           string;
  filename:     string;
  sizeBytes:    number;
  status:       "processing" | "ready" | "error";
  chunkCount:   number;
  uploadedAt:   string;
  processedAt:  string | null;
  errorMsg:     string | null;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("pl-PL", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

const STATUS_META = {
  processing: { label: "Przetwarzanie…", color: "text-yellow-600 dark:text-yellow-400", dot: "bg-yellow-400 animate-pulse" },
  ready:      { label: "Gotowy",         color: "text-green-600 dark:text-green-400",  dot: "bg-green-500" },
  error:      { label: "Błąd",           color: "text-red-600 dark:text-red-400",      dot: "bg-red-500" },
};

export default function DocumentsPage() {
  const { data: session } = useSession();
  const [docs,      setDocs]      = useState<PrivateDoc[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [dragOver,  setDragOver]  = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const tier = session?.user?.tier ?? "free";
  const canUpload = ["pro", "kancelaria"].includes(tier);

  async function loadDocs() {
    const res = await fetch("/api/private-docs");
    if (res.ok) setDocs(await res.json());
    setLoading(false);
  }

  useEffect(() => {
    void loadDocs();
    // Poll dla dokumentów w trakcie przetwarzania
    const interval = setInterval(() => {
      if (docs.some((d) => d.status === "processing")) void loadDocs();
    }, 3000);
    return () => clearInterval(interval);
  }, [docs.some((d) => d.status === "processing")]);

  async function handleUpload(file: File) {
    setError(null);
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    const res  = await fetch("/api/private-docs", { method: "POST", body: form });
    const data = await res.json() as { error?: string };
    if (!res.ok) {
      setError(data.error ?? "Błąd uploadu.");
    } else {
      void loadDocs();
    }
    setUploading(false);
  }

  async function handleDelete(id: string) {
    if (!confirm("Usunąć dokument i jego indeks?")) return;
    await fetch(`/api/private-docs/${id}`, { method: "DELETE" });
    setDocs((d) => d.filter((doc) => doc.id !== id));
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleUpload(file);
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <header className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <a href="/ask" className="text-blue-600 dark:text-blue-400 hover:underline text-sm">← Wróć</a>
          <span className="text-slate-300 dark:text-slate-600">|</span>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Moje dokumenty</h1>
          <span className="ml-auto text-xs text-slate-400">
            {docs.filter((d) => d.status === "ready").length} / 20 dokumentów
          </span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">

        {/* Blokada */}
        {!canUpload && (
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl p-6 text-center">
            <p className="font-semibold text-blue-800 dark:text-blue-200 mb-1">Dostępne od planu Pro</p>
            <p className="text-sm text-blue-600 dark:text-blue-400 mb-4">
              Wgraj własne umowy i pisma — system będzie odpowiadał uwzględniając Twoje dokumenty.
            </p>
            <a href="/upgrade" className="inline-block px-5 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors">
              Przejdź na Pro
            </a>
          </div>
        )}

        {/* Upload zone */}
        {canUpload && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`border-2 border-dashed rounded-2xl p-10 text-center transition-colors cursor-pointer ${
              dragOver
                ? "border-blue-400 bg-blue-50 dark:bg-blue-900/20"
                : "border-slate-300 dark:border-slate-600 hover:border-blue-400 bg-white dark:bg-slate-800"
            }`}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.docx"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUpload(f); }}
            />
            {uploading ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
                <p className="text-sm text-slate-500">Przesyłanie…</p>
              </div>
            ) : (
              <>
                <svg className="w-10 h-10 mx-auto mb-3 text-slate-300 dark:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="font-medium text-slate-700 dark:text-slate-300">Przeciągnij plik lub kliknij</p>
                <p className="text-sm text-slate-400 mt-1">PDF, TXT, DOCX · max 10 MB</p>
              </>
            )}
          </div>
        )}

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-xl px-4 py-3">
            {error}
          </p>
        )}

        {/* Lista dokumentów */}
        {!loading && docs.length > 0 && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
            <ul className="divide-y divide-slate-100 dark:divide-slate-700">
              {docs.map((doc) => {
                const st = STATUS_META[doc.status];
                return (
                  <li key={doc.id} className="px-5 py-4 flex items-center gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className="font-medium text-slate-800 dark:text-slate-200 text-sm truncate">{doc.filename}</p>
                        <div className="flex items-center gap-1 shrink-0">
                          <span className={`w-2 h-2 rounded-full ${st.dot}`} />
                          <span className={`text-xs ${st.color}`}>{st.label}</span>
                        </div>
                      </div>
                      <p className="text-xs text-slate-400 dark:text-slate-500">
                        {formatSize(doc.sizeBytes)} · {formatDate(doc.uploadedAt)}
                        {doc.status === "ready" && ` · ${doc.chunkCount} fragmentów`}
                        {doc.errorMsg && ` · ${doc.errorMsg}`}
                      </p>
                    </div>
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 shrink-0 transition-colors"
                    >
                      Usuń
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Info */}
        {canUpload && (
          <div className="bg-slate-50 dark:bg-slate-800/50 rounded-2xl border border-slate-200 dark:border-slate-700 p-5 text-sm text-slate-600 dark:text-slate-400 space-y-2">
            <p className="font-medium text-slate-700 dark:text-slate-300">Jak to działa?</p>
            <ol className="list-decimal list-inside space-y-1 text-xs">
              <li>Wgrywasz dokumenty (umowy, opinie, pisma procesowe)</li>
              <li>System automatycznie dzieli je na fragmenty i indeksuje</li>
              <li>Gdy zadajesz pytanie na <a href="/ask" className="text-blue-600 hover:underline">/ask</a>, system przeszukuje <strong>oba</strong> korpusy: publiczny (ISAP/SAOS) i Twoje dokumenty</li>
              <li>Odpowiedź zawiera cytowania zarówno z prawa, jak i z Twoich dokumentów</li>
            </ol>
          </div>
        )}
      </main>
    </div>
  );
}
