import { useEffect, useState } from 'react';
import { Link2, Loader2, Search, Sparkles, X } from 'lucide-react';
import { askOrkg, ensureApiKey, resolveOrkg } from '@/services/api';

export type ImportMode = 'query' | 'links';
export type OrkgItem = Record<string, unknown> & { id?: string; label?: string; title?: string; year?: number | string; resolved?: boolean };

type Props = {
  open: boolean;
  mode: ImportMode;
  onClose: () => void;
  onUseQuery: (query: string) => void;
  onUseLinks: (records: OrkgItem[]) => void;
};

export function ImportModal({ open, mode, onClose, onUseQuery, onUseLinks }: Props) {
  const [tab, setTab] = useState<ImportMode>(mode);
  const [q, setQ] = useState('');
  const [links, setLinks] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState<OrkgItem[]>([]);
  const [retrievalMode, setRetrievalMode] = useState('');
  const [resolved, setResolved] = useState<OrkgItem[]>([]);
  const [unresolvedCount, setUnresolvedCount] = useState(0);

  useEffect(() => {
    if (open) { setTab(mode); setError(''); setResults([]); setRetrievalMode(''); setResolved([]); setUnresolvedCount(0); }
  }, [open, mode]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!open) return null;

  const runSearch = async () => {
    if (!q.trim()) return;
    setLoading(true); setError(''); setResults([]); setRetrievalMode('');
    try {
      await ensureApiKey();
      const r = await askOrkg(q.trim(), 15);
      setResults((r.records as OrkgItem[]) || []);
      setRetrievalMode(r.mode === 'sparql' ? 'Retrieved via generated SPARQL' : 'Retrieved via ORKG search');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'ORKG retrieval failed.');
    } finally {
      setLoading(false);
    }
  };

  const runResolve = async () => {
    if (!links.trim()) return;
    setLoading(true); setError(''); setResolved([]); setUnresolvedCount(0);
    try {
      await ensureApiKey();
      const r = await resolveOrkg(links.trim());
      setResolved((r.records as OrkgItem[]) || []);
      setUnresolvedCount(r.unresolved.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Resolving references failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4"
      style={{ background: 'rgba(2,6,23,0.45)', backdropFilter: 'blur(2px)' }}
      onMouseDown={onClose}
    >
      <div
        className="panel mt-[8vh] w-full max-w-xl p-5"
        style={{ boxShadow: 'var(--shadow-lg)' }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-bold" style={{ color: 'var(--heading)' }}>Import from ORKG</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>

        <div className="mb-4 flex gap-1">
          <button className={`tab ${tab === 'query' ? 'active' : ''}`} onClick={() => setTab('query')}>Ask ORKG</button>
          <button className={`tab ${tab === 'links' ? 'active' : ''}`} onClick={() => setTab('links')}>Paste links</button>
        </div>

        {tab === 'query' ? (
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
              What would you like to find in ORKG?
            </label>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="e.g. machine learning approaches for malaria detection (2020–2025)"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void runSearch(); }}
              />
              <button className="btn btn-soft" onClick={() => void runSearch()} disabled={loading || !q.trim()}>
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />} Search
              </button>
            </div>

            {error && <p className="mt-3 banner-error">{error}</p>}

            {retrievalMode && (
              <p className="mt-3 text-xs font-medium" style={{ color: 'var(--indigo)' }}>
                {retrievalMode} · {results.length} result{results.length === 1 ? '' : 's'}
              </p>
            )}
            {results.length > 0 && (
              <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
                {results.map((it, i) => (
                  <div key={i} className="rounded-lg p-2 text-sm" style={{ border: '1px solid var(--border)' }}>
                    <p className="font-medium" style={{ color: 'var(--heading)' }}>
                      {String(it.title || it.label || Object.values(it).find((v) => typeof v === 'string' && v) || 'Untitled')}
                    </p>
                    {it.year ? <p className="text-xs" style={{ color: 'var(--muted)' }}>{String(it.year)}</p> : null}
                  </div>
                ))}
              </div>
            )}

            <p className="mt-3 text-xs" style={{ color: 'var(--faint)' }}>
              These ORKG sources are attached to your next Generate, which turns them into a
              literature review or comparison table.
            </p>

            <div className="mt-4 flex justify-end gap-2">
              <button className="btn btn-soft" onClick={onClose}>Cancel</button>
              <button
                className="btn btn-generate"
                disabled={!q.trim()}
                onClick={() => { onUseQuery(q.trim()); onClose(); }}
              >
                <Sparkles size={15} /> Use these sources
              </button>
            </div>
          </div>
        ) : (
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
              Paste ORKG links, ORKG ids, DOIs, or paper titles (one per line, or comma-separated for ids/DOIs)
            </label>
            <textarea
              className="input h-36"
              placeholder={'https://orkg.org/paper/R12345\n10.1109/ACCESS.2021.0000000\nDeep learning for malaria detection'}
              value={links}
              onChange={(e) => setLinks(e.target.value)}
            />
            <div className="mt-3 flex justify-end">
              <button className="btn btn-soft" onClick={() => void runResolve()} disabled={loading || !links.trim()}>
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Link2 size={15} />} Resolve
              </button>
            </div>

            {error && <p className="mt-3 banner-error">{error}</p>}

            {resolved.length > 0 && (
              <>
                <p className="mt-2 text-xs font-medium" style={{ color: 'var(--indigo)' }}>
                  Resolved {resolved.length - unresolvedCount}/{resolved.length} references
                  {unresolvedCount ? ` · ${unresolvedCount} unresolved` : ''}
                </p>
                <div className="mt-2 max-h-56 space-y-1 overflow-y-auto">
                  {resolved.map((it, i) => (
                    <div key={i} className="rounded-lg p-2 text-sm" style={{ border: '1px solid var(--border)' }}>
                      <p className="font-medium" style={{ color: 'var(--heading)' }}>
                        {String(it.title || it.label || it.input || 'Untitled')}
                      </p>
                      <p className="text-xs" style={{ color: it.resolved ? 'var(--muted)' : 'var(--danger)' }}>
                        {it.resolved ? (it.orkg_id ? `ORKG ${it.orkg_id}` : (it.doi ? `DOI ${it.doi}` : 'resolved')) : 'not found in ORKG'}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button className="btn btn-soft" onClick={onClose}>Cancel</button>
              <button
                className="btn btn-generate"
                disabled={resolved.length === 0}
                onClick={() => { onUseLinks(resolved); onClose(); }}
              >
                <Link2 size={15} /> Add {resolved.length || ''} sources
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
