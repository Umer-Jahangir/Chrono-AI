import { NavLink } from 'react-router-dom';

export default function MobileNavDrawer({ isOpen, onClose }) {
  return (
    <>
      <div 
        onClick={onClose}
        className={`fixed inset-0 bg-gray-900/40 z-40 xl:hidden transition-opacity duration-300 ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
      ></div>

      <aside className={`fixed bottom-0 left-0 top-0 z-50 flex h-full w-[min(84vw,300px)] flex-col overflow-y-auto bg-surface p-4 transition-transform duration-300 xl:hidden ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex items-center justify-between mb-6">
          <span className="font-headline-lg text-title-lg tracking-tight text-on-surface">Chrono AI</span>
          <button onClick={onClose} type="button" aria-label="Close menu" className="w-9 h-9 flex items-center justify-center rounded-full text-on-surface-variant hover:bg-surface-container-low transition-colors">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <nav className="flex flex-col gap-1">
          <NavLink to="/" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive ? 'font-semibold text-primary bg-primary/10' : 'font-medium text-on-surface hover:bg-surface-container-low'}`}>
            {({ isActive }) => (
              <><span className={`material-symbols-outlined text-[20px] ${isActive ? 'text-primary' : 'text-on-surface-variant'}`}>home</span> Home</>
            )}
          </NavLink>
          <NavLink to="/dashboard" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive ? 'font-semibold text-primary bg-primary/10' : 'font-medium text-on-surface hover:bg-surface-container-low'}`}>
            {({ isActive }) => (
              <><span className={`material-symbols-outlined text-[20px] ${isActive ? 'text-primary' : 'text-on-surface-variant'}`}>dashboard</span> Dashboard</>
            )}
          </NavLink>
          <NavLink to="/timeline" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive ? 'font-semibold text-primary bg-primary/10' : 'font-medium text-on-surface hover:bg-surface-container-low'}`}>
            {({ isActive }) => (
              <><span className={`material-symbols-outlined text-[20px] ${isActive ? 'text-primary' : 'text-on-surface-variant'}`}>history</span> Timeline</>
            )}
          </NavLink>
          <NavLink to="/search" onClick={onClose} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${isActive ? 'font-semibold text-primary bg-primary/10' : 'font-medium text-on-surface hover:bg-surface-container-low'}`}>
            {({ isActive }) => (
              <><span className={`material-symbols-outlined text-[20px] ${isActive ? 'text-primary' : 'text-on-surface-variant'}`}>search</span> Search</>
            )}
          </NavLink>
        </nav>
      </aside>
    </>
  );
}
