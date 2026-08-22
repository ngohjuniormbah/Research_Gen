import { useState } from 'react';
import {
  FileText, FolderOpen, MoreHorizontal, Pencil, Plus, Search, Star,
} from 'lucide-react';

export type WorkItem = { id: string; title: string; date: string; pages: number; starred?: boolean };

const TABS = ['All', 'Recent', 'Starred', 'Archived'] as const;

export function RecentWork({ items, onNew }: { items: WorkItem[]; onNew: () => void }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('All');
  const [q, setQ] = useState('');

  const filtered = items.filter((it) => {
    if (tab === 'Starred' && !it.starred) return false;
    if (q && !it.title.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  return (
    <aside className="flex w-[360px] shrink-0 flex-col px-5 py-6" style={{ borderLeft: '1px solid var(--border)' }}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold" style={{ color: 'var(--heading)' }}>Recent Work</h2>
        <button className="icon-btn" onClick={onNew} title="New" aria-label="New project"><Plus size={16} /></button>
      </div>

      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--faint)' }} />
        <input
          className="input pl-9" placeholder="Search projects..." value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div className="mb-4 flex items-center gap-1">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto">
        {filtered.length === 0 && (
          <p className="px-1 py-6 text-center text-sm" style={{ color: 'var(--muted)' }}>No projects yet.</p>
        )}
        {filtered.map((it) => (
          <div key={it.id} className="group flex items-start gap-3 rounded-xl p-3 card-hover" style={{ border: '1px solid transparent' }}>
            <span className="mt-0.5 rounded-lg p-1.5" style={{ background: 'var(--indigo-soft)', color: 'var(--indigo)' }}>
              <FileText size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-semibold" style={{ color: 'var(--heading)' }}>{it.title}</p>
              <p className="mt-0.5 text-xs" style={{ color: 'var(--muted)' }}>{it.date} · {it.pages} pages</p>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--faint)' }}>
              <Star size={15} fill={it.starred ? 'var(--star)' : 'none'} style={{ color: it.starred ? 'var(--star)' : 'var(--faint)' }} />
              <Pencil size={14} />
              <MoreHorizontal size={15} />
            </div>
          </div>
        ))}
      </div>

      <button className="btn btn-soft mt-4 w-full">
        <FolderOpen size={15} /> View all projects
      </button>
    </aside>
  );
}
