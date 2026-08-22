import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BookOpen, Check, Download, Loader2, Moon, Search as SearchIcon, Send, Sparkles, Sun, X,
} from 'lucide-react';
import {
  createSession, deleteSession, ensureApiKey, exportReview, getSession, listModels,
  listSessions, multiReview, orkgConnect, orkgConnection, orkgDisconnect, orkgDraft,
  resolveOrkg, streamChat, streamReview, updateSession, uploadDocument,
} from '@/services/api';
import type { BackendModel, MultiReviewItem, ReviewOut, SourceRecord } from '@/types';
import type { OrkgItem } from '@/components/ImportModal';
import { guessKind } from '@/data/formats';
import { downloadBlob, uid } from '@/utils/helpers';
import { Sidebar, type NavKey } from '@/components/Sidebar';
import { RecentWork, type WorkItem } from '@/components/RecentWork';
import { Composer, type FileItem } from '@/components/Composer';
import { ImportModal, type ImportMode } from '@/components/ImportModal';
import { Markdown } from '@/components/Markdown';

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

const fmtDate = (iso: string) => {
  try { return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch { return ''; }
};

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [nav, setNav] = useState<NavKey>('new');

  const [models, setModels] = useState<BackendModel[]>([]);
  const [selected, setSelected] = useState('');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [ready, setReady] = useState(false);

  const [multiResults, setMultiResults] = useState<MultiReviewItem[] | null>(null);
  const [multiTab, setMultiTab] = useState(0);

  const [prompt, setPrompt] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);
  const [orkgQuery, setOrkgQuery] = useState('');
  const [orkgRecords, setOrkgRecords] = useState<OrkgItem[]>([]);

  const [working, setWorking] = useState(false);
  const [streamText, setStreamText] = useState('');
  const streamRef = useRef('');
  const [review, setReview] = useState<ReviewOut | null>(null);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState('');

  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<ImportMode>('query');
  const [modelsOpen, setModelsOpen] = useState(false);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [orkgConnected, setOrkgConnected] = useState<boolean | null>(null);
  const [orkgUser, setOrkgUser] = useState('');
  const [orkgPass, setOrkgPass] = useState('');
  const [orkgBusy, setOrkgBusy] = useState(false);
  const [orkgMsg, setOrkgMsg] = useState('');

  const [work, setWork] = useState<WorkItem[]>([]);
  const [workLoading, setWorkLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const [chatTurns, setChatTurns] = useState<{ role: string; text: string }[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [chatStream, setChatStream] = useState('');
  const chatRef = useRef('');

  useEffect(() => {
    try { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('wms.theme', theme); } catch { /* ignore */ }
  }, [theme]);

  const refreshWork = useCallback(async (q?: string) => {
    setWorkLoading(true);
    try {
      await ensureApiKey();
      const rows = await listSessions(q, true);
      setWork(rows.map((r) => ({
        id: r.id, title: r.title || 'Untitled research', date: fmtDate(r.updated_at),
        pages: Math.max(r.outputs, r.sources), starred: r.starred, archived: r.archived,
      })));
    } catch { /* offline; keep existing */ } finally { setWorkLoading(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try { await ensureApiKey(); } catch { /* generate retries */ }
      try {
        const d = await listModels();
        if (!cancelled) {
          setModels(d.providers);
          setSelected((c) => (d.providers.some((p) => p.key === c) ? c : d.default));
          setSelectedModels((c) => (c.length ? c : [d.default]));
        }
      } catch { /* offline */ }
      if (!cancelled) { setReady(true); void refreshWork(); }
    })();
    return () => { cancelled = true; };
  }, [refreshWork]);

  const addFiles = useCallback(async (list: FileList | File[]) => {
    for (const file of Array.from(list)) {
      const item: FileItem = { id: uid(), name: file.name, kind: guessKind(file.name), size: file.size, status: 'uploading' };
      setFiles((x) => [...x, item]);
      try {
        await ensureApiKey();
        const d = await uploadDocument(file);
        setFiles((x) => x.map((v) => (v.id === item.id ? { ...v, status: d.status === 'parsed' ? 'parsed' : 'failed', docId: d.id, error: d.error } : v)));
      } catch (e) {
        setFiles((x) => x.map((v) => (v.id === item.id ? { ...v, status: 'failed', error: e instanceof Error ? e.message : 'Upload failed' } : v)));
      }
    }
  }, []);

  const removeFile = (id: string) => setFiles((x) => x.filter((f) => f.id !== id));

  // Persist the current research context (Working Memory) after a generation.
  const saveSession = useCallback(async (rev: ReviewOut, topic: string) => {
    const state = {
      prompt: topic,
      model: selected,
      orkg_query: orkgQuery,
      orkg_records: orkgRecords,
      files: files.map((f) => ({ id: f.id, name: f.name, kind: f.kind, size: f.size, docId: f.docId, status: f.status })),
      outputs: [rev],
    };
    try {
      if (sessionId) {
        await updateSession(sessionId, { title: topic, state });
      } else {
        const created = await createSession({ title: topic, state });
        setSessionId(created.id);
      }
      void refreshWork();
    } catch { /* non-fatal: the review still shows */ }
  }, [selected, orkgQuery, orkgRecords, files, sessionId, refreshWork]);

  const generate = useCallback(async () => {
    if (!prompt.trim() || working || !ready) return;
    setWorking(true); setError(''); setReview(null); setMultiResults(null);
    setStreamText(''); streamRef.current = '';
    const docIds = files.filter((f) => f.status === 'parsed' && f.docId).map((f) => f.docId!);
    const topic = prompt.trim();
    // If the user pasted ORKG links / DOIs directly into the prompt bar, resolve them
    // against ORKG and add them as sources (so "paste a link and generate" just works).
    let pasted: OrkgItem[] = [];
    if (/orkg\.org\/|\b10\.\d{4,9}\/|https?:\/\//i.test(topic)) {
      try { pasted = (await resolveOrkg(topic)).records as OrkgItem[]; } catch { /* ignore */ }
    }
    const records: SourceRecord[] = [...orkgRecords, ...pasted]
      .filter((r) => r.resolved !== false)
      .map((r) => ({
        title: String(r.title || r.label || r.input || ''),
        abstract: String(r.abstract || ''),
        authors: [],
        year: typeof r.year === 'number' ? r.year
          : (typeof r.year === 'string' && /^\d{4}$/.test(r.year) ? Number(r.year) : null),
        venue: '',
        doi: String(r.doi || ''),
        full_text: null,
        raw: { orkg_id: r.orkg_id ?? null, source: r.source ?? null },
      }));
    const base = {
      topic,
      document_ids: docIds,
      records: records.length ? records : undefined,
      orkg_query: orkgQuery.trim() || undefined,
      max_tokens: 4000, // allow long, multi-section / multi-table reviews (avoid truncation)
    };
    const provs = (selectedModels.length ? selectedModels : (selected ? [selected] : [])).filter(Boolean);

    // Multi-LLM: run the same dataset+prompt through each model, show them separately.
    if (provs.length > 1) {
      try {
        const r = await multiReview({ ...base, providers: provs });
        setMultiResults(r.results); setMultiTab(0);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Generation failed.');
      } finally {
        setWorking(false);
      }
      return;
    }

    // Single model: live token stream.
    await streamReview(
      { ...base, provider: provs[0] || undefined },
      {
        onToken: (t) => { streamRef.current += t; setStreamText(streamRef.current); },
        onDone: (d) => {
          const rev: ReviewOut = {
            id: d.review_id, job_id: null, topic: d.topic || topic, provider: d.provider,
            model: d.model, content_md: streamRef.current, structured: d.structured,
            csl_json: [], created_at: new Date().toISOString(),
          };
          setReview(rev); setStreamText(''); setWorking(false); setChatTurns([]);
          void saveSession(rev, topic);
        },
        onError: (e) => { setError(e.message); setWorking(false); },
      },
    );
    setWorking(false);
  }, [prompt, working, ready, selected, selectedModels, files, orkgQuery, orkgRecords, saveSession]);

  const pickMultiResult = useCallback((item: MultiReviewItem) => {
    const rev: ReviewOut = {
      id: item.review_id || '', job_id: null, topic: prompt.trim(), provider: item.provider,
      model: item.model, content_md: item.content_md, structured: item.structured,
      csl_json: [], created_at: new Date().toISOString(),
    };
    setReview(rev); setMultiResults(null); setChatTurns([]);
    void saveSession(rev, prompt.trim());
  }, [prompt, saveSession]);

  const doExport = useCallback(async (format: 'md' | 'pdf' | 'docx') => {
    if (!review) return;
    setExporting(format); setError('');
    try { const { blob, filename } = await exportReview(review.id, format); downloadBlob(blob, filename); }
    catch (e) { setError(e instanceof Error ? e.message : 'Export failed.'); }
    finally { setExporting(''); }
  }, [review]);

  const resetToNew = useCallback(() => {
    setReview(null); setError(''); setStreamText(''); streamRef.current = '';
    setPrompt(''); setFiles([]); setOrkgQuery(''); setOrkgRecords([]); setSessionId(null);
    setChatTurns([]); setChatStream(''); chatRef.current = ''; setMultiResults(null);
  }, []);

  const sendChat = useCallback(async () => {
    const q = chatInput.trim();
    if (!q || !sessionId || chatBusy) return;
    setChatTurns((t) => [...t, { role: 'user', text: q }]);
    setChatInput(''); setChatBusy(true); setChatStream(''); chatRef.current = '';
    await streamChat(sessionId, q, {
      provider: selected || undefined,
      onToken: (t) => { chatRef.current += t; setChatStream(chatRef.current); },
      onDone: () => { setChatTurns((t) => [...t, { role: 'assistant', text: chatRef.current }]); setChatStream(''); setChatBusy(false); },
      onError: (e) => { setChatTurns((t) => [...t, { role: 'assistant', text: `⚠ ${e.message}` }]); setChatStream(''); setChatBusy(false); },
    });
    setChatBusy(false);
  }, [chatInput, sessionId, chatBusy, selected]);

  // Reopen a saved research session — restore the full Working-Memory state.
  const openSession = useCallback(async (id: string) => {
    setError('');
    try {
      await ensureApiKey();
      const s = await getSession(id);
      const st = s.state || {};
      setSessionId(s.id);
      setPrompt(String(st.prompt || ''));
      if (st.model) setSelected(String(st.model));
      setOrkgQuery(String(st.orkg_query || ''));
      setOrkgRecords(Array.isArray(st.orkg_records) ? st.orkg_records : []);
      setFiles(Array.isArray(st.files) ? st.files.map((f: Record<string, unknown>) => ({
        id: String(f.id || uid()), name: String(f.name || 'file'), kind: String(f.kind || 'unknown'),
        size: Number(f.size || 0), status: (f.status as FileItem['status']) || 'parsed',
        docId: f.docId as string | undefined,
      })) : []);
      const outputs = Array.isArray(st.outputs) ? st.outputs : [];
      setReview(outputs.length ? (outputs[outputs.length - 1] as ReviewOut) : null);
      setChatTurns(Array.isArray(st.chat) ? st.chat : []);
      setChatStream(''); chatRef.current = '';
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not open this session.'); }
  }, []);

  const removeSession = useCallback(async (id: string) => {
    if (!window.confirm('Delete this research session? This cannot be undone.')) return;
    try {
      await deleteSession(id);
      setWork((w) => w.filter((it) => it.id !== id));
      if (sessionId === id) resetToNew();
    } catch (e) { setError(e instanceof Error ? e.message : 'Delete failed.'); }
  }, [sessionId, resetToNew]);

  const renameWork = useCallback(async (id: string, current: string) => {
    const next = window.prompt('Rename research session', current);
    if (!next || !next.trim() || next.trim() === current) return;
    try { await updateSession(id, { title: next.trim() }); void refreshWork(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Rename failed.'); }
  }, [refreshWork]);

  const toggleStar = useCallback(async (id: string) => {
    const cur = work.find((w) => w.id === id);
    try { await updateSession(id, { starred: !cur?.starred }); void refreshWork(); }
    catch { /* ignore */ }
  }, [work, refreshWork]);

  const toggleArchive = useCallback(async (id: string, archived: boolean) => {
    try { await updateSession(id, { archived }); void refreshWork(); }
    catch { /* ignore */ }
  }, [refreshWork]);

  const openImport = (m: ImportMode) => { setImportMode(m); setImportOpen(true); };

  const openSettings = useCallback(async () => {
    setSettingsOpen(true); setOrkgMsg('');
    try { await ensureApiKey(); setOrkgConnected((await orkgConnection()).connected); }
    catch { setOrkgConnected(false); }
  }, []);
  const connectOrkg = useCallback(async () => {
    if (!orkgUser || !orkgPass || orkgBusy) return;
    setOrkgBusy(true); setOrkgMsg('');
    try {
      const s = await orkgConnect(orkgUser, orkgPass);
      setOrkgConnected(s.connected); setOrkgPass('');
      setOrkgMsg(s.connected ? 'Connected to ORKG.' : 'Could not connect.');
    } catch (e) { setOrkgMsg(e instanceof Error ? e.message : 'Connection failed.'); }
    finally { setOrkgBusy(false); }
  }, [orkgUser, orkgPass, orkgBusy]);
  const disconnectOrkg = useCallback(async () => {
    setOrkgBusy(true);
    try { await orkgDisconnect(); setOrkgConnected(false); setOrkgMsg('Disconnected.'); }
    catch { /* ignore */ } finally { setOrkgBusy(false); }
  }, []);
  const doOrkgDraft = useCallback(async () => {
    if (!review) return;
    setExporting('orkg'); setError('');
    try { const { blob, filename } = await orkgDraft(review.id); downloadBlob(blob, filename); }
    catch (e) { setError(e instanceof Error ? e.message : 'ORKG draft failed.'); }
    finally { setExporting(''); }
  }, [review]);

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: 'var(--panel)' }}>
      <div className="flex h-full flex-col overflow-hidden">
        {/* Header */}
        <header className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-6 py-4" style={{ borderBottom: '1px solid var(--divider)' }}>
          <div className="flex items-center">
            <span className="rounded-xl p-2" style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}><BookOpen size={20} /></span>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-extrabold tracking-tight sm:text-2xl md:text-4xl" style={{ color: 'var(--heading)' }}>World Model Of Science</h1>
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
          <Sidebar active={nav} onSelect={(k) => { setNav(k); if (k === 'models') setModelsOpen(true); if (k === 'settings') void openSettings(); if (k === 'new') resetToNew(); }} />

          <main className="flex flex-1 flex-col items-center overflow-y-auto px-4 py-10 sm:px-6">
            {multiResults && !review ? (
              <div className="w-full max-w-3xl">
                <div className="mb-4 flex items-center justify-between">
                  <button className="btn btn-soft" onClick={resetToNew}>← New research</button>
                  <p className="text-sm font-semibold" style={{ color: 'var(--heading)' }}>
                    {multiResults.length} models · pick one to continue
                  </p>
                </div>
                <div className="mb-3 flex flex-wrap gap-1">
                  {multiResults.map((m, i) => (
                    <button key={i} className={`tab ${multiTab === i ? 'active' : ''}`} onClick={() => setMultiTab(i)}>
                      {m.provider}{m.error ? ' ⚠' : ''}
                    </button>
                  ))}
                </div>
                {multiResults[multiTab] && (
                  <div className="card p-6">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-xs" style={{ color: 'var(--muted)' }}>
                        {toText(multiResults[multiTab].provider)}{multiResults[multiTab].model ? ` · ${toText(multiResults[multiTab].model)}` : ''}
                      </p>
                      {!multiResults[multiTab].error && (
                        <button className="btn btn-generate" onClick={() => pickMultiResult(multiResults[multiTab])}>
                          Use this result
                        </button>
                      )}
                    </div>
                    <div className="review-body">
                      {multiResults[multiTab].error
                        ? <p style={{ color: 'var(--danger)' }}>{toText(multiResults[multiTab].error)}</p>
                        : <Markdown text={toText(multiResults[multiTab].content_md)} />}
                    </div>
                  </div>
                )}
              </div>
            ) : !review && !working ? (
              <div className="flex w-full max-w-2xl flex-col items-center" style={{ marginTop: '8vh' }}>
                <Sparkles size={30} style={{ color: 'var(--blue)' }} />
                <h2 className="mt-4 text-center text-3xl font-extrabold" style={{ color: 'var(--heading)' }}>Welcome to your research workspace</h2>
                <p className="mt-2 max-w-md text-center text-[0.95rem]" style={{ color: 'var(--muted)' }}>
                  Explore, analyze, and synthesize scientific knowledge.
                </p>
                <div className="mt-8 w-full">
                  <Composer
                    prompt={prompt} setPrompt={setPrompt} working={working} ready={ready}
                    onGenerate={generate} onFiles={addFiles} files={files} onRemoveFile={removeFile}
                    onOpenLinks={() => openImport('links')} onOpenQuery={() => openImport('query')}
                  />
                  {(orkgQuery || orkgRecords.length > 0) && (
                    <div className="mt-3 flex flex-wrap justify-center gap-2">
                      {orkgQuery && (
                        <span className="chip"><SearchIcon size={13} style={{ color: 'var(--indigo)' }} /> ORKG: {orkgQuery.slice(0, 40)}
                          <button onClick={() => setOrkgQuery('')} aria-label="Remove"><X size={12} /></button></span>
                      )}
                      {orkgRecords.length > 0 && (
                        <span className="chip">ORKG sources ({orkgRecords.filter((r) => r.resolved !== false).length})
                          <button onClick={() => setOrkgRecords([])} aria-label="Remove"><X size={12} /></button></span>
                      )}
                    </div>
                  )}
                  {error && <div className="mt-4 banner-error">{error}</div>}
                </div>
              </div>
            ) : (
              <div className="w-full max-w-3xl">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <button className="btn btn-soft" onClick={resetToNew} disabled={working}>← New research</button>
                  {review && !working && (
                    <div className="flex gap-2">
                      {(['md', 'pdf', 'docx'] as const).map((fmt) => (
                        <button key={fmt} className="btn btn-soft" disabled={!!exporting} onClick={() => void doExport(fmt)}>
                          {exporting === fmt ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                          {fmt === 'md' ? 'Markdown' : fmt === 'pdf' ? 'PDF' : 'Word'}
                        </button>
                      ))}
                      <button className="btn btn-soft" disabled={!!exporting} onClick={() => void doOrkgDraft()} title="Structured ORKG submission draft (not auto-published)">
                        {exporting === 'orkg' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                        ORKG draft
                      </button>
                    </div>
                  )}
                </div>
                <div className="card p-6">
                  <h3 className="text-xl font-bold" style={{ color: 'var(--heading)' }}>{toText(review ? review.topic : prompt)}</h3>
                  {review && !working && (
                    <p className="mt-1 text-xs" style={{ color: 'var(--muted)' }}>{toText(review.provider)}{review.model ? ` · ${toText(review.model)}` : ''}</p>
                  )}
                  <div className="review-body mt-4">
                    {working ? (
                      <><Markdown text={streamText || 'Thinking…'} /><span className="stream-cursor" /></>
                    ) : (
                      <Markdown text={toText(review?.content_md)} />
                    )}
                  </div>
                </div>

                {review && !working && sessionId && (
                  <div className="card mt-4 p-4">
                    <p className="mb-3 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
                      Ask follow-up questions about this research (grounded in your sources)
                    </p>
                    <div className="space-y-2">
                      {chatTurns.map((m, i) => (
                        <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div
                            className="max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm"
                            style={m.role === 'user'
                              ? { background: 'var(--blue)', color: '#fff' }
                              : { background: 'var(--panel-soft)', border: '1px solid var(--border)', color: 'var(--text)' }}
                          >
                            {m.role === 'user' ? toText(m.text) : <div className="review-body"><Markdown text={m.text} /></div>}
                          </div>
                        </div>
                      ))}
                      {chatBusy && (
                        <div className="flex justify-start">
                          <div className="max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm" style={{ background: 'var(--panel-soft)', border: '1px solid var(--border)', color: 'var(--text)' }}>
                            {chatStream || 'Thinking…'}<span className="stream-cursor" />
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <input
                        className="input flex-1"
                        placeholder="e.g. Which paper reports the highest accuracy? Make a comparison table."
                        value={chatInput}
                        onChange={(e) => setChatInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendChat(); } }}
                        disabled={chatBusy}
                      />
                      <button className="btn btn-generate" disabled={chatBusy || !chatInput.trim()} onClick={() => void sendChat()} aria-label="Send">
                        {chatBusy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                      </button>
                    </div>
                  </div>
                )}

                {error && <div className="mt-4 banner-error">{error}</div>}
              </div>
            )}
          </main>

          <RecentWork
            items={work} loading={workLoading}
            onOpen={openSession} onDelete={removeSession} onRename={renameWork}
            onToggleStar={toggleStar} onToggleArchive={toggleArchive}
            onSearch={(q) => void refreshWork(q)}
          />
        </div>
      </div>

      <ImportModal
        open={importOpen} mode={importMode} onClose={() => setImportOpen(false)}
        onUseQuery={(v) => setOrkgQuery(v)} onUseLinks={(recs) => setOrkgRecords(recs)}
      />

      {modelsOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4" style={{ background: 'rgba(2,6,23,0.45)', backdropFilter: 'blur(2px)' }} onMouseDown={() => setModelsOpen(false)}>
          <div className="panel mt-[10vh] w-full max-w-md p-5" style={{ boxShadow: 'var(--shadow-lg)' }} onMouseDown={(e) => e.stopPropagation()}>
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-base font-bold" style={{ color: 'var(--heading)' }}>Choose model(s)</h3>
              <button className="icon-btn" onClick={() => setModelsOpen(false)} aria-label="Close"><X size={16} /></button>
            </div>
            <p className="mb-3 text-xs" style={{ color: 'var(--muted)' }}>
              Select one or more. With multiple, each model generates a separate result to compare.
            </p>
            <div className="space-y-1.5">
              {models.length === 0 && <p className="text-sm" style={{ color: 'var(--muted)' }}>Loading models…</p>}
              {models.map((m) => {
                const on = selectedModels.includes(m.key);
                return (
                  <button
                    key={m.key}
                    className={`nav-item ${on ? 'active-green' : ''}`}
                    onClick={() => {
                      const next = on ? selectedModels.filter((k) => k !== m.key) : [...selectedModels, m.key];
                      setSelectedModels(next);
                      setSelected(next[0] || m.key);
                    }}
                  >
                    <span className="flex h-4 w-4 items-center justify-center rounded" style={{ border: '1.5px solid var(--border-strong)', background: on ? 'var(--accent)' : 'transparent', color: 'var(--accent-fg)' }}>
                      {on ? <Check size={12} /> : null}
                    </span>
                    {m.label || m.key}{m.location ? ` — ${m.location}` : ''}
                  </button>
                );
              })}
            </div>
            <button className="btn btn-generate mt-4 w-full" onClick={() => setModelsOpen(false)}>
              Done{selectedModels.length > 1 ? ` (${selectedModels.length} models)` : ''}
            </button>
          </div>
        </div>
      )}

      {settingsOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4" style={{ background: 'rgba(2,6,23,0.45)', backdropFilter: 'blur(2px)' }} onMouseDown={() => setSettingsOpen(false)}>
          <div className="panel mt-[10vh] w-full max-w-md p-5" style={{ boxShadow: 'var(--shadow-lg)' }} onMouseDown={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-bold" style={{ color: 'var(--heading)' }}>Settings — connect ORKG</h3>
              <button className="icon-btn" onClick={() => setSettingsOpen(false)} aria-label="Close"><X size={16} /></button>
            </div>
            <p className="mb-3 text-xs" style={{ color: 'var(--muted)' }}>
              Connect your ORKG account to access your resources. Credentials are sent only to
              the backend (server-side OIDC) and are never stored in the browser.
            </p>
            {orkgConnected ? (
              <div>
                <p className="mb-3 flex items-center gap-2 text-sm" style={{ color: 'var(--ok)' }}>
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: 'var(--ok)' }} /> Connected to ORKG
                </p>
                <button className="btn btn-soft w-full" disabled={orkgBusy} onClick={() => void disconnectOrkg()}>
                  {orkgBusy ? <Loader2 size={14} className="animate-spin" /> : null} Disconnect
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <input className="input" placeholder="ORKG email / username" value={orkgUser} onChange={(e) => setOrkgUser(e.target.value)} />
                <input className="input" type="password" placeholder="ORKG password" value={orkgPass} onChange={(e) => setOrkgPass(e.target.value)} />
                <button className="btn btn-generate w-full" disabled={orkgBusy || !orkgUser || !orkgPass} onClick={() => void connectOrkg()}>
                  {orkgBusy ? <Loader2 size={16} className="animate-spin" /> : null} Connect
                </button>
              </div>
            )}
            {orkgMsg && <p className="mt-3 text-xs" style={{ color: orkgConnected ? 'var(--ok)' : 'var(--muted)' }}>{orkgMsg}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
