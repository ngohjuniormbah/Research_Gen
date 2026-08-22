import {
  ChevronsLeft, Folder, Library, PlusCircle, Settings, Share2,
} from 'lucide-react';

export type NavKey = 'new' | 'projects' | 'sources' | 'models' | 'settings';

const ITEMS: { key: NavKey; label: string; icon: typeof Folder }[] = [
  { key: 'new', label: 'New Review', icon: PlusCircle },
  { key: 'projects', label: 'Projects', icon: Folder },
  { key: 'sources', label: 'Sources', icon: Library },
  { key: 'models', label: 'Models', icon: Share2 },
  { key: 'settings', label: 'Settings', icon: Settings },
];

export function Sidebar({ active, onSelect }: { active: NavKey; onSelect: (k: NavKey) => void }) {
  return (
    <nav className="flex w-56 shrink-0 flex-col justify-between px-4 py-6" style={{ borderRight: '1px solid var(--border)' }}>
      <div className="flex flex-col gap-1.5">
        {ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`nav-item ${active === key ? 'active-green' : ''}`}
            onClick={() => onSelect(key)}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </div>
      <button className="icon-btn self-start" title="Collapse" aria-label="Collapse sidebar">
        <ChevronsLeft size={16} />
      </button>
    </nav>
  );
}
