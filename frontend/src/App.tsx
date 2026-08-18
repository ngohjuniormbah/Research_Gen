import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BookOpen, Database, Download, FileText, Loader2, Moon, Paperclip, Send, Sun, X,
} from 'lucide-react';
import {
  createReview, ensureApiKey, exportReview, getReview, health, listModels, pollJob,
  uploadDocument,
} from '@/services/api';
import type { BackendModel, ReviewOut } from '@/types';
import { ACCEPT, formatLabel, guessKind } from '@/data/formats';
import { bytes, downloadBlob, uid } from '@/utils/helpers';

type Theme = 'light' | 'dark';
type FileItem = {
  id: string; name: string; kind: string; size: number;
  status: 'uploading' | 'parsed' | 'failed'; docId?: string; error?: string;
};

function initialTheme(): Theme {
  const saved = localStorage.getItem('research-gen.theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [online, setOnline] = useState<boolean | null>(null);

  const [models, setModels] = useState<BackendModel[]>([]);
  const [selected, setSelected] = useState('');
  const [modelError, setModelError] = useState('');

  const [files, setFiles] = useState<FileItem[]>([]);
  const [prompt, setPrompt] = useState('');

  const [ready, setReady] = useState(false);
  const [working, setWorking] = useState(false);
  const [progress, setProgress] = useState(0);
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  const fileInput = useRef<HTMLInputElement>(null);

  // Apply + persist theme.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('research-gen.theme', theme);
  }, [theme]);

  // Load the model list (public) and silently provision an API key for uploads.
  const loadModels = useCallback(async () => {
    setModelError('');
    try {
      const d = await listModels();
      setModels(d.providers);
      setSelected((cur) => (d.providers.some((p) => p.key === cur) ? cur : d.default));
    } catch (e) {
      setModelError(e instanceof Error ? e.message : 'Could not load models.');
    }
  }, []);

  // Initialise once: provision the key, then load the picker. Only when both are done
  // do we mark the app ready — Generate stays disabled until then, so a click on a fresh
  // page can't run against a half-initialised state (the "blank until you refresh" bug).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try { await ensureApiKey(); } catch { /* generate() retries the key if this failed */ }
      await loadModels();
      if (!cancelled) setReady(true);
    })();
    return () => { cancelled = true; };
  }, [loadModels]);

  // Backend health, retried to ride out a cold start.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let i = 0; i < 12; i++) {
        try {
          const x = await health();
          if (x.ok) { if (!cancelled) setOnline(true); return; }
        } catch { /* transient cold start */ }
        if (cancelled) return;
        await new Promise((r) => setTimeout(r, i === 0 ? 1000 : 4000));
      }
      if (!cancelled) setOnline(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const addFiles = useCallback(async (list: FileList | File[]) => {
    for (const file of Array.from(list)) {
      const item: FileItem = {
        id: uid(), name: file.name, kind: guessKind(file.name), size: file.size, status: 'uploading',
      };
      setFiles((x) => [...x, item]);
      try {
        await ensureApiKey();
        const d = await uploadDocument(file);
        setFiles((x) => x.map((v) => (v.id === item.id
          ? { ...v, status: d.status === 'parsed' ? 'parsed' : 'failed', docId: d.id, error: d.error }
          : v)));
      } catch (e) {
        setFiles((x) => x.map((v) => (v.id === item.id
          ? { ...v, status: 'failed', error: e instanceof Error ? e.message : 'Upload failed' }
          : v)));
      }
    }
  }, []);

  const removeFile = (id: string) => setFiles((x) => x.filter((f) => f.id !== id));

  const generate = useCallback(async () => {
    if (!prompt.trim() || working || !selected || !ready) return;
    setWorking(true); setError(''); setReview(null); setProgress(0);
    const docIds = files.filter((f) => f.status === 'parsed' && f.docId).map((f) => f.docId!);
    try {
      await ensureApiKey();
      const job = await createReview({ topic: prompt.trim(), provider: selected, document_ids: docIds });
      const done = await pollJob(job.id, (j) => setProgress(j.progress));
      const reviewId = done.result.review_id as string | undefined;
      if (!reviewId) throw new Error('Job finished without a review id.');
      setReview(await getReview(reviewId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setWorking(false); setProgress(0);
    }
  }, [prompt, working, selected, files, ready]);

  const doExport = useCallback(async (format: 'md' | 'pdf' | 'docx') => {
    if (!review) return;
    setExporting(format); setError('');
    try {
      const { blob, filename } = await exportReview(review.id, format);
      downloadBlob(blob, filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed.');
    } finally {
      setExporting('');
    }
  }, [review]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void generate(); }
  };

  const sections = review?.structured?.sections ?? [];

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header
        className="sticky top-0 z-10 flex items-center justify-between px-4 py-3 sm:px-6"
        style={{ background: 'var(--panel)', borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-3">
          <div className="rounded-xl p-2" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
            <BookOpen size={18} />
          </div>
          <div>
            <h1 className="text-[15px] font-semibold leading-tight">Research_Gen</h1>
            <p className="text-[11px]" style={{ color: 'var(--muted)' }}>Literature Review Generator</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--muted)' }}>
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: online === true ? 'var(--ok)' : online === false ? 'var(--danger)' : 'var(--faint)' }}
            />
            {online === true ? 'Backend online' : online === false ? 'Backend offline' : 'Checking…'}
          </span>
          <button
            className="icon-btn"
            onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold">Generate a literature review</h2>
          <p className="mt-1 text-sm" style={{ color: 'var(--muted)' }}>
            Import your sources, type your subject, pick a model, and generate.
          </p>
        </div>

        {/* Composer */}
        <div className="card p-4 sm:p-5">
          {/* 1. Import data */}
          <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
            1 · Import your data (CSV, Excel, PDF, JSON)
          </label>
          <div
            className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center"
            style={{ borderColor: 'var(--border)', background: 'var(--panel-2)' }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files.length) void addFiles(e.dataTransfer.files); }}
          >
            <Paperclip size={18} style={{ color: 'var(--muted)' }} />
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              Drag &amp; drop files here, or{' '}
              <button className="underline" style={{ color: 'var(--accent)' }} onClick={() => fileInput.current?.click()}>
                browse
              </button>
            </p>
            <input
              ref={fileInput} type="file" multiple accept={ACCEPT} className="hidden"
              onChange={(e) => { if (e.target.files?.length) void addFiles(e.target.files); e.target.value = ''; }}
            />
          </div>

          {files.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {files.map((f) => (
                <span key={f.id} className="chip">
                  {f.status === 'uploading'
                    ? <Loader2 size={13} className="animate-spin" />
                    : <FileText size={13} style={{ color: f.status === 'failed' ? 'var(--danger)' : 'var(--accent)' }} />}
                  <span className="max-w-[160px] truncate">{f.name}</span>
                  <span style={{ color: 'var(--faint)' }}>· {formatLabel(f.kind)} · {bytes(f.size)}</span>
                  {f.status === 'failed' && <span style={{ color: 'var(--danger)' }}>· failed</span>}
                  <button onClick={() => removeFile(f.id)} aria-label="Remove"><X size={12} /></button>
                </span>
              ))}
            </div>
          )}

          {/* 2. Prompt */}
          <label className="mb-2 mt-5 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
            2 · Your subject / prompt
          </label>
          <textarea
            className="input" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. Transformer architectures for machine translation…"
          />

          {/* 3. Model + generate */}
          <label className="mb-2 mt-5 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
            3 · Choose a model
          </label>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <select className="input sm:flex-1" value={selected} onChange={(e) => setSelected(e.target.value)}>
              {models.length === 0 && <option value="">Loading models…</option>}
              {models.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label || m.key}{m.location ? ` — ${m.location}` : ''}
                </option>
              ))}
            </select>
            <button
              className="btn btn-primary sm:w-auto"
              disabled={working || !ready || !prompt.trim() || !selected}
              onClick={() => void generate()}
            >
              {working || !ready ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              {working ? 'Generating…' : !ready ? 'Preparing…' : 'Generate'}
            </button>
          </div>

          {modelError && <p className="mt-3 banner-error">{modelError}</p>}
        </div>

        {/* Result */}
        {error && <div className="mt-5 banner-error">{error}</div>}

        {working && (
          <div className="card mt-5 flex items-center gap-3 p-4 text-sm" style={{ color: 'var(--muted)' }}>
            <Loader2 size={16} className="animate-spin" />
            Working… {progress ? `${Math.round(progress * 100)}%` : ''}
          </div>
        )}

        {review && !working && (
          <div className="card mt-5 p-4 sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">{review.topic}</h3>
                <p className="text-xs" style={{ color: 'var(--muted)' }}>
                  {review.provider}{review.model ? ` · ${review.model}` : ''}
                </p>
              </div>
              <div className="flex gap-2">
                {(['md', 'pdf', 'docx'] as const).map((fmt) => (
                  <button key={fmt} className="btn btn-ghost" disabled={!!exporting} onClick={() => void doExport(fmt)}>
                    {exporting === fmt ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    {fmt === 'md' ? 'Markdown' : fmt === 'pdf' ? 'PDF' : 'Word'}
                  </button>
                ))}
              </div>
            </div>
            <div className="review">
              {sections.length > 0
                ? sections.map((s, i) => (
                    <div key={i}>
                      <h3>{s.heading}</h3>
                      <p>{s.content}</p>
                    </div>
                  ))
                : <p>{review.content_md}</p>}
            </div>
          </div>
        )}

        {!review && !working && (
          <div className="card mt-5 flex items-center justify-center gap-2 p-8 text-sm" style={{ color: 'var(--muted)' }}>
            <Database size={16} /> No review yet — import sources and generate one above.
          </div>
        )}
      </main>
    </div>
  );
}
