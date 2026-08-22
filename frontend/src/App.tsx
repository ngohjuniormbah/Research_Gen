import { useCallback, useEffect, useState } from 'react';
import {
  BookOpen, Download, Loader2, Moon, Search as SearchIcon, Sparkles, Sun, X,
} from 'lucide-react';
import {
  createReview, ensureApiKey, exportReview, getReview, listModels, pollJob, uploadDocument,
} from '@/services/api';
import type { BackendModel, ReviewOut } from '@/types';
import { guessKind } from '@/data/formats';
import { downloadBlob, uid } from '@/utils/helpers';
import { Sidebar, type NavKey } from '@/components/Sidebar';
import { RecentWork, type WorkItem } from '@/components/RecentWork';
import { Composer, type FileItem } from '@/components/Composer';
import { ImportModal, type ImportMode } from '@/components/ImportModal';

type Theme = 'light' | 'dark';

function toText(v: unknown): string {
  if (typeof v === 'string') return v;
  if (v == null) return '';
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (Array.isArray(v)) return v.map(toText).join('\n');
  try { return JSON.stringify(v); } catch { return String(v); }
}

function initialTheme(): Theme {
  try {
    const s = localStorage.getItem('wms.theme');
    if (s === 'light' || s === 'dark') return s;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch { return 'light'; }
}

const SAMPLE_WORK: WorkItem[] = [
  { id: 's1', title: 'Malaria & Bone Marrow Research', date: 'May 20, 2025', pages: 23, starred: true },
  { id: 's2', title: 'Breast Cancer Biomarkers Review', date: 'May 18, 2025', pages: 18 },
  { id: 's3', title: 'Cervical Cancer Treatment Advances', date: 'May 15, 2025', pages: 15 },
  { id: 's4', title: 'AI in Medical Diagnosis', date: 'May 10, 2025', pages: 31 },
  { id: 's5', title: 'Nanoparticles in Drug Delivery', date: 'May 8, 2025', pages: 12 },
];

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [nav, setNav] = useState<NavKey>('new');

  const [models, setModels] = useState<BackendModel[]>([]);
  const [selected, setSelected] = useState('');
  const [ready, setReady] = useState(false);

  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [orkgQuery, setOrkgQuery] = useState('');
  const [links, setLinks] = useState('');

  const [working, setWorking] = useState(false);
  const [progress, setProgress] = useState(0);
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>('query');
  const [modelsOpen, setModelsOpen] = useState(false);
  const [work, setWork] = useState<WorkItem[]>(SAMPLE_WORK);

  useEffect(() => {
    try { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('wms.theme', theme); } catch { /* ignore */ }
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try { await ensureApiKey(); } catch { /* generate retries */ }
      try {
        const d = await listModels();
        if (!cancelled) { setModels(d.providers); setSelected((c) => (d.providers.some((p) => p.key === c) ? c : d.default)); }
      } catch { /* offline; generate will surface it */ }
      if (!cancelled) setReady(true);
    })();
    return () => { cancelled = true; };
  }, []);

  const addFiles = useCallback(async (list: FileList | File[]) => {
    for (const file of Array.from(list)) {
      const item: FileItem = { id: uid(), name: file.name, kind: guessKind(file.name), size: file.size, status: 'uploading' };
      setFiles((x) => [...x, item]);
      try {
        await ensureApiKey();
        const d = await uploadDocument(file);
        setFiles((x) => x.map((v) => (v.id === item.id
          ? { ...v, status: d.status === 'parsed' ? 'parsed' : 'failed', docId: d.id, error: d.error } : v)));
      } catch (e) {
        setFiles((x) => x.map((v) => (v.id === item.id
          ? { ...v, status: 'failed', error: e instanceof Error ? e.message : 'Upload failed' } : v)));
      }
    }
  }, []);

  const removeFile = (id: string) => setFiles((x) => x.filter((f) => f.id !== id));

  const generate = useCallback(async () => {
    if (!prompt.trim() || working || !ready) return;
    setWorking(true); setError(''); setReview(null); setProgress(0);
    const docIds = files.filter((f) => f.status === 'parsed' && f.docId).map((f) => f.docId!);
    try {
      await ensureApiKey();
      const job = await createReview({
        topic: prompt.trim(),
        provider: selected || undefined,
        document_ids: docIds,
        orkg_query: orkgQuery.trim() || undefined,
        instructions: links.trim() ? `Also consider these references:\n${links.trim()}` : undefined,
      });
      const done = await pollJob(job.id, (j) => setProgress(j.progress));
      const reviewId = done.result.review_id as string | undefined;
      if (!reviewId) throw new Error('Job finished without a review id.');
      const rev = await getReview(reviewId);
      setReview(rev);
      setWork((w) => [{
        id: rev.id, title: rev.topic || prompt.trim().slice(0, 60),
        date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
        pages: (rev.structured?.sections?.length ?? 1),
      }, ...w]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setWorking(false); setProgress(0);
    }
  }, [prompt, working, ready, selected, files, orkgQuery, links]);

  const doExport = useCallback(async (format: 'md' | 'pdf' | 'docx') => {
    if (!review) return;
    setExporting(format); setError('');
    try { const { blob, filename } = await exportReview(review.id, format); downloadBlob(blob, filename); }
    catch (e) { setError(e instanceof Error ? e.message : 'Export failed.'); }
    finally { setExporting(''); }
  }, [review]);

  const openImport = (m: ImportMode) => { setImportMode(m); setImportOpen(true); };
  const resetToNew = () => { setReview(null); setError(''); };
  const sections = review?.structured?.sections ?? [];

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--panel)' }}>
      <div className="flex h-full flex-col overflow-hidden">
        {/* Header */}
        <header className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-6 py-4" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center">
            <span className="rounded-xl p-2" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}><BookOpen size={20} /></span>
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-extrabold tracking-tight" style={{ color: 'var(--heading)' }}>World Model Of Science</h1>
            <p className="text-sm font-medium" style={{ color: 'var(--muted)' }}>Working Memory</p>
          </div>
          <div className="flex justify-end">
            <div className="toggle-group">
              <button className={`toggle-btn ${theme === 'light' ? 'active' : ''}`} onClick={() => setTheme('light')} aria-label="Light theme"><Sun size={17} /></button>
              <button className={`toggle-btn ${theme === 'dark' ? 'active' : ''}`} onClick={() => setTheme('dark')} aria-label="Dark theme"><Moon size={17} /></button>
            </div>
          </div>
        </header>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          <Sidebar active={nav} onSelect={(k) => { setNav(k); if (k === 'models') setModelsOpen(true); if (k === 'new') resetToNew(); }} />

          {/* Center */}
          <main className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-6 py-10">
            {!review ? (
              <div className="flex w-full max-w-2xl flex-col items-center">
                <Sparkles size={30} style={{ color: 'var(--blue)' }} />
                <h2 className="mt-4 text-center text-3xl font-extrabold" style={{ color: 'var(--heading)' }}>Welcome to your research workspace</h2>
                <p className="mt-2 max-w-md text-center text-[0.95rem]" style={{ color: 'var(--muted)' }}>
                  Ask anything, import your sources, and let AI help you build high-quality research.
                </p>

                <div className="mt-8 w-full">
                  <Composer
                    prompt={prompt} setPrompt={setPrompt} working={working} ready={ready}
                    onGenerate={generate} onFiles={addFiles} files={files} onRemoveFile={removeFile}
                    onOpenLinks={() => openImport('links')} onOpenQuery={() => openImport('query')}
                  />
                  {(orkgQuery || links) && (
                    <div className="mt-3 flex flex-wrap justify-center gap-2">
                      {orkgQuery && (
                        <span className="chip"><SearchIcon size={13} style={{ color: 'var(--indigo)' }} /> ORKG: {orkgQuery.slice(0, 40)}
                          <button onClick={() => setOrkgQuery('')} aria-label="Remove"><X size={12} /></button></span>
                      )}
                      {links && (
                        <span className="chip">Links ({links.split('\n').filter(Boolean).length})
                          <button onClick={() => setLinks('')} aria-label="Remove"><X size={12} /></button></span>
                      )}
                    </div>
                  )}
                  {error && <div className="mt-4 banner-error">{error}</div>}
                  {working && (
                    <div className="mt-4 flex items-center justify-center gap-2 text-sm" style={{ color: 'var(--muted)' }}>
                      <Loader2 size={15} className="animate-spin" /> Working… {progress ? `${Math.round(progress * 100)}%` : ''}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="w-full max-w-3xl">
                <div className="mb-4 flex items-center justify-between">
                  <button className="btn btn-soft" onClick={resetToNew}>← New research</button>
                  <div className="flex gap-2">
                    {(['md', 'pdf', 'docx'] as const).map((fmt) => (
                      <button key={fmt} className="btn btn-soft" disabled={!!exporting} onClick={() => void doExport(fmt)}>
                        {exporting === fmt ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                        {fmt === 'md' ? 'Markdown' : fmt === 'pdf' ? 'PDF' : 'Word'}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="card p-6">
                  <h3 className="text-xl font-bold" style={{ color: 'var(--heading)' }}>{toText(review.topic)}</h3>
                  <p className="mt-1 text-xs" style={{ color: 'var(--muted)' }}>{toText(review.provider)}{review.model ? ` · ${toText(review.model)}` : ''}</p>
                  <div className="review-body mt-4">
                    {sections.length > 0
                      ? sections.map((s, i) => (<div key={i}><h3>{toText(s.heading)}</h3><p>{toText(s.content)}</p></div>))
                      : <p>{toText(review.content_md)}</p>}
                  </div>
                </div>
                {error && <div className="mt-4 banner-error">{error}</div>}
              </div>
            )}
          </main>

          <RecentWork items={work} onNew={resetToNew} />
        </div>
      </div>

      <ImportModal
        open={importOpen} mode={importMode} onClose={() => setImportOpen(false)}
        onUseQuery={(v) => setOrkgQuery(v)} onUseLinks={(v) => setLinks(v)}
      />

      {modelsOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4" style={{ background: 'rgba(2,6,23,0.45)', backdropFilter: 'blur(2px)' }} onMouseDown={() => setModelsOpen(false)}>
          <div className="panel mt-[10vh] w-full max-w-md p-5" style={{ boxShadow: 'var(--shadow-lg)' }} onMouseDown={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-bold" style={{ color: 'var(--heading)' }}>Choose a model</h3>
              <button className="icon-btn" onClick={() => setModelsOpen(false)} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="space-y-1.5">
              {models.length === 0 && <p className="text-sm" style={{ color: 'var(--muted)' }}>Loading models…</p>}
              {models.map((m) => (
                <button
                  key={m.key}
                  className={`nav-item ${selected === m.key ? 'active-green' : ''}`}
                  onClick={() => { setSelected(m.key); setModelsOpen(false); }}
                >
                  {m.label || m.key}{m.location ? ` — ${m.location}` : ''}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
