import { useEffect, useState } from 'react';
import { Globe, Link2, Loader2, Search, Sparkles, X } from 'lucide-react';
import { askOrkg, ensureApiKey, resolveOrkg, searchSources } from '@/services/api';

export type ImportMode = 'sources' | 'query' | 'links';
export type OrkgItem = Record<string, unknown> & { id?: string; label?: string; title?: string; year?: number | string; resolved?: boolean; provider?: string };

type Props = {
  open: boolean;
  mode: ImportMode;
  onClose: () => void;
  onUseQuery: (query: string) => void;
  onUseLinks: (records: OrkgItem[]) => void;
};

// Each real source gets a stable colored badge so results read like multi-source search.
const PROVIDER_COLORS: Record<string, string> = {
  OpenAlex: '#2563eb', Crossref: '#b45309', arXiv: '#b91c1c', ORKG: '#7c3aed',
};
function ProviderBadge({ name }: { name?: string }) {
  const label = name || 'Source';
  const color = PROVIDER_COLORS[label] || '#64748b';
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.7rem] font-semibold"
      style={{ background: `${color}1a`, color }}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} /> {label}
    </span>
  );
}

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
  // Multi-source (web) search state.
  const [webQ, setWebQ] = useState('');
  const [webResults, setWebResults] = useState<OrkgItem[]>([]);
  const [webProviders, setWebProviders] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setTab(mode); setError(''); setResults([]); setRetrievalMode('');
      setResolved([]); setUnresolvedCount(0); setWebResults([]); setWebProviders([]);
    }
  }, [open, mode]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  if (!open) return null;

  const runWebSearch = async () => {
    if (!webQ.trim()) return;
    setLoading(true); setError(''); setWebResults([]); setWebProviders([]);
    try {
      await ensureApiKey();
      const r = await searchSources(webQ.trim(), 12);
      setWebResults((r.records as OrkgItem[]) || []);
      setWebProviders(r.providers || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Source search failed.');
    } finally { setLoading(false); }
  };

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
    } finally { setLoading(false); }
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
    } finally { setLoading(false); }
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
          <h3 className="text-base font-bold" style={{ color: 'var(--heading)' }}>Import sources</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>

        <div className="mb-4 flex gap-1">
          <button className={`tab ${tab === 'sources' ? 'active' : ''}`} onClick={() => setTab('sources')}>All sources</button>
          <button className={`tab ${tab === 'query' ? 'active' : ''}`} onClick={() => setTab('query')}>ORKG</button>
          <button className={`tab ${tab === 'links' ? 'active' : ''}`} onClick={() => setTab('links')}>Paste links</button>
        </div>

        {tab === 'sources' ? (
          <div>
            <label className="mb-2 block text-xs font-medium" style={{ color: 'var(--muted)' }}>
              Search real scholarly sources at once (OpenAlex, Crossref, arXiv)
            </label>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="e.g. deep learning for malaria detection"
                value={webQ}
                onChange={(e) => setWebQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void runWebSearch(); }}
              />
              <button className="btn btn-soft" onClick={() => void runWebSearch()} disabled={loading || !webQ.trim()}>
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Globe size={15} />} Search
              </button>
            </div>

            {error && <p className="mt-3 banner-error">{error}</p>}

            {webProviders.length > 0 && (
              <p className="mt-3 text-xs font-medium" style={{ color: 'var(--muted)' }}>
                {webResults.length} result{webResults.length === 1 ? '' : 's'} from {webProviders.length} sources
              </p>
            )}
            {webResults.length > 0 && (
              <div className="mt-2 max-h-72 space-y-1.5 overflow-y-auto">
                {webResults.map((it, i) => (
                  <div key={i} className="rounded-lg p-2.5 text-sm" style={{ border: '1px solid var(--border)' }}>
                    <div className="mb-1 flex items-center gap-2">
                      <ProviderBadge name={it.provider} />
                      {Array.isArray(it.also_in) && (it.also_in as string[]).map((p) => <ProviderBadge key={p} name={p} />)}
                      {it.year ? <span className="text-xs" style={{ color: 'var(--faint)' }}>{String(it.year)}</span> : null}
                    </div>
                    <p className="font-medium" style={{ color: 'var(--heading)' }}>
                      {String(it.title || it.label || 'Untitled')}
                    </p>
                    {it.doi ? <p className="text-xs" style={{ color: 'var(--muted)' }}>doi:{String(it.doi)}</p> : null}
                  </div>
                ))}
              </div>
            )}

            <p className="mt-3 text-xs" style={{ color: 'var(--faint)' }}>
              Attached results become sources for your next Generate — grounded in the real papers found.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn btn-soft" onClick={onClose}>Cancel</button>
              <button className="btn btn-generate" disabled={webResults.length === 0}
                onClick={() => { onUseLinks(webResults); onClose(); }}>
                <Sparkles size={15} /> Add {webResults.length || ''} sources
              </button>
            </div>
          </div>
        ) : tab === 'query' ? (
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
