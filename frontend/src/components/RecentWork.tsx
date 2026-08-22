import { useState } from 'react';
import {
  FileText, FolderOpen, Loader2, MoreHorizontal, Pencil, Search, Star, Trash2,
} from 'lucide-react';

export type WorkItem = { id: string; title: string; date: string; pages: number; starred?: boolean };

const TABS = ['All', 'Recent', 'Starred', 'Archived'] as const;

type Props = {
  items: WorkItem[];
  loading?: boolean;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, current: string) => void;
  onToggleStar: (id: string) => void;
};

export function RecentWork({ items, loading, onOpen, onDelete, onRename, onToggleStar }: Props) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('All');
  const [q, setQ] = useState('');
  const [menuId, setMenuId] = useState<string | null>(null);

  const filtered = items.filter((it) => {
    if (tab === 'Starred' && !it.starred) return false;
    if (q && !it.title.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  return (
    <aside className="flex w-[360px] shrink-0 flex-col px-5 py-6" style={{ borderLeft: '1px solid var(--divider)' }}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold" style={{ color: 'var(--heading)' }}>Recent Work</h2>
        {loading && <Loader2 size={15} className="animate-spin" style={{ color: 'var(--faint)' }} />}
      </div>

      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--faint)' }} />
        <input className="input pl-9" placeholder="Search past work..." value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className="mb-4 flex items-center gap-1">
        {TABS.map((t) => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto">
        {filtered.length === 0 && (
          <p className="px-1 py-6 text-center text-sm" style={{ color: 'var(--muted)' }}>
            {q ? 'No matching work.' : 'No past work yet — generate your first review.'}
          </p>
        )}
        {filtered.map((it) => (
          <div
            key={it.id}
            className="group relative flex items-start gap-3 rounded-xl p-3 card-hover"
            style={{ border: '1px solid transparent' }}
            onClick={() => onOpen(it.id)}
          >
            <span className="mt-0.5 rounded-lg p-1.5" style={{ background: 'var(--indigo-soft)', color: 'var(--indigo)' }}>
              <FileText size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-semibold" style={{ color: 'var(--heading)' }}>{it.title}</p>
              <p className="mt-0.5 text-xs" style={{ color: 'var(--muted)' }}>{it.date} · {it.pages} pages</p>
            </div>
            <div className="flex items-center gap-1.5" style={{ color: 'var(--faint)' }} onClick={(e) => e.stopPropagation()}>
              <button title={it.starred ? 'Unstar' : 'Star'} onClick={() => onToggleStar(it.id)}>
                <Star size={15} fill={it.starred ? 'var(--star)' : 'none'} style={{ color: it.starred ? 'var(--star)' : 'var(--faint)' }} />
              </button>
              <button title="Rename" onClick={() => onRename(it.id, it.title)}><Pencil size={14} /></button>
              <button title="More" onClick={() => setMenuId((m) => (m === it.id ? null : it.id))}><MoreHorizontal size={15} /></button>
            </div>
            {menuId === it.id && (
              <div className="menu absolute right-3 top-11 z-20 w-36 p-1.5" onClick={(e) => e.stopPropagation()}>
                <button className="menu-item" onClick={() => { setMenuId(null); onOpen(it.id); }}>
                  <FolderOpen size={15} /> Open
                </button>
                <button className="menu-item" onClick={() => { setMenuId(null); onRename(it.id, it.title); }}>
                  <Pencil size={15} /> Rename
                </button>
                <button className="menu-item" style={{ color: 'var(--danger)' }} onClick={() => { setMenuId(null); onDelete(it.id); }}>
                  <Trash2 size={15} /> Delete
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <button className="btn btn-soft mt-4 w-full" onClick={() => setTab('All')}>
        <FolderOpen size={15} /> View all projects
      </button>
    </aside>
  );
}
