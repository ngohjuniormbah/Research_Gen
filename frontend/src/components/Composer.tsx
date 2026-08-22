import { useEffect, useRef, useState } from 'react';
import {
  Braces, FileSpreadsheet, FileText, Link2, Loader2, Plus, Search, X,
} from 'lucide-react';
import { bytes } from '@/utils/helpers';
import { formatLabel } from '@/data/formats';

export type FileItem = {
  id: string; name: string; kind: string; size: number;
  status: 'uploading' | 'parsed' | 'failed'; docId?: string; error?: string;
};

type Props = {
  prompt: string;
  setPrompt: (v: string) => void;
  working: boolean;
  ready: boolean;
  onGenerate: () => void;
  onFiles: (files: FileList | File[]) => void;
  onOpenLinks: () => void;
  onOpenQuery: () => void;
  files: FileItem[];
  onRemoveFile: (id: string) => void;
};

export function Composer(p: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [accept, setAccept] = useState('*');
  const fileInput = useRef<HTMLInputElement>(null);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setMenuOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (acc: string) => { setAccept(acc); setMenuOpen(false); setTimeout(() => fileInput.current?.click(), 0); };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); p.onGenerate(); }
  };

  return (
    <div ref={wrap} className="relative w-full max-w-2xl">
      <div className="composer p-4">
        <textarea
          className="w-full resize-none bg-transparent text-[0.95rem] outline-none"
          style={{ color: 'var(--text)', minHeight: '2.4rem' }}
          rows={2}
          value={p.prompt}
          onChange={(e) => p.setPrompt(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="What would you like to research?"
        />

        {p.files.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {p.files.map((f) => (
              <span key={f.id} className="chip">
                {f.status === 'uploading'
                  ? <Loader2 size={13} className="animate-spin" />
                  : <FileText size={13} style={{ color: f.status === 'failed' ? 'var(--danger)' : 'var(--accent)' }} />}
                <span className="max-w-[150px] truncate">{f.name}</span>
                <span style={{ color: 'var(--faint)' }}>· {formatLabel(f.kind)} · {bytes(f.size)}</span>
                {f.status === 'failed' && (
                  <span style={{ color: 'var(--danger)' }} title={f.error || 'failed'}>· {f.error ? f.error.slice(0, 48) : 'failed'}</span>
                )}
                <button onClick={() => p.onRemoveFile(f.id)} aria-label="Remove"><X size={12} /></button>
              </span>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between">
          <button
            className="icon-btn"
            style={{ background: 'var(--panel-soft)' }}
            onClick={() => setMenuOpen((o) => !o)}
            aria-label="Add sources"
          >
            <Plus size={18} />
          </button>
          <button
            className="btn btn-generate px-6"
            disabled={p.working}
            onClick={p.onGenerate}
          >
            {p.working ? <Loader2 size={16} className="animate-spin" /> : null}
            {p.working ? 'Generating…' : !p.ready ? 'Preparing…' : 'Generate'}
          </button>
        </div>
      </div>

      <input
        ref={fileInput} type="file" multiple accept={accept} className="hidden"
        onChange={(e) => { if (e.target.files?.length) p.onFiles(e.target.files); e.target.value = ''; }}
      />

      {menuOpen && (
        <div className="menu absolute left-2 top-full z-20 mt-2 w-64 p-2">
          <button className="menu-item" onClick={() => pick('.csv,text/csv')}>
            <FileSpreadsheet size={17} style={{ color: '#16a34a' }} /> CSV File
          </button>
          <button className="menu-item" onClick={() => pick('.pdf,application/pdf')}>
            <FileText size={17} style={{ color: '#dc2626' }} /> PDF File
          </button>
          <button className="menu-item" onClick={() => pick('.json,.jsonld,application/json')}>
            <Braces size={17} style={{ color: '#6366f1' }} /> JSON File
          </button>
          <button className="menu-item" onClick={() => { setMenuOpen(false); p.onOpenLinks(); }}>
            <Link2 size={17} style={{ color: 'var(--muted)' }} /> Links (Title, DOI, URL)
          </button>
          <button className="menu-item" onClick={() => { setMenuOpen(false); p.onOpenQuery(); }}>
            <Search size={17} style={{ color: 'var(--muted)' }} /> Query
          </button>
        </div>
      )}
    </div>
  );
}
