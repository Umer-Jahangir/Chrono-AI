import { NavLink } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';

function safePictureUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

export default function Header({ onToggleDrawer }) {
  const { user, logout } = useAuth();
  const pictureUrl = safePictureUrl(user?.picture_url);
  return (
    <header className="fixed left-0 top-0 z-50 flex h-16 w-full min-w-0 items-center justify-between gap-3 border-b border-outline-variant/30 bg-surface px-3 sm:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button 
          onClick={onToggleDrawer} 
          type="button" 
          aria-label="Toggle menu" 
          className="mr-1 inline-flex h-9 w-9 items-center justify-center rounded-md text-on-surface transition-colors hover:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 xl:hidden"
        >
          <span className="material-symbols-outlined">menu</span>
        </button>
        <div className="flex min-w-0 items-center justify-center text-on-surface">
          <span className="truncate text-lg font-semibold tracking-tight text-on-surface sm:text-xl">Chrono AI</span>
        </div>
      </div>

      <nav className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-6 xl:flex">
        <NavLink to="/" className={({ isActive }) => `group relative text-sm font-medium transition-colors py-5 ${isActive ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-primary'}`}>
          {({ isActive }) => (
            <>
              Home
              <span className={`absolute left-0 -bottom-px h-0.5 w-full bg-primary origin-center transition-transform duration-300 ease-out ${isActive ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'}`}></span>
            </>
          )}
        </NavLink>
        <NavLink to="/dashboard" className={({ isActive }) => `group relative text-sm font-medium transition-colors py-5 ${isActive ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-primary'}`}>
          {({ isActive }) => (
            <>
              Dashboard
              <span className={`absolute left-0 -bottom-px h-0.5 w-full bg-primary origin-center transition-transform duration-300 ease-out ${isActive ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'}`}></span>
            </>
          )}
        </NavLink>
        <NavLink to="/timeline" className={({ isActive }) => `group relative text-sm font-medium transition-colors py-5 ${isActive ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-primary'}`}>
          {({ isActive }) => (
            <>
              Timeline
              <span className={`absolute left-0 -bottom-px h-0.5 w-full bg-primary origin-center transition-transform duration-300 ease-out ${isActive ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'}`}></span>
            </>
          )}
        </NavLink>
        <NavLink to="/search" className={({ isActive }) => `group relative text-sm font-medium transition-colors py-5 ${isActive ? 'text-primary font-semibold' : 'text-on-surface-variant hover:text-primary'}`}>
          {({ isActive }) => (
            <>
              Search
              <span className={`absolute left-0 -bottom-px h-0.5 w-full bg-primary origin-center transition-transform duration-300 ease-out ${isActive ? 'scale-x-100' : 'scale-x-0 group-hover:scale-x-100'}`}></span>
            </>
          )}
        </NavLink>
      </nav>

      <div className="flex items-center gap-2 sm:gap-3">
        <div className="hidden min-w-0 items-center gap-2 md:flex">
          {pictureUrl ? (
            <img
              src={pictureUrl}
              alt=""
              referrerPolicy="no-referrer"
              className="w-8 h-8 rounded-full object-cover border border-outline-variant/30"
            />
          ) : (
            <span className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center material-symbols-outlined text-lg" aria-hidden="true">person</span>
          )}
          <span className="max-w-28 truncate text-sm text-on-surface 2xl:max-w-48" title={user?.display_name || user?.email}>
            {user?.display_name || user?.email}
          </span>
        </div>
        <button
          type="button"
          onClick={logout}
          className="inline-flex h-10 flex-shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-outline-variant/40 px-3 text-sm font-medium text-on-surface transition hover:bg-primary/5 hover:text-primary active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          aria-label="Sign out of Chrono"
        >
          <span className="material-symbols-outlined text-[19px]" aria-hidden="true">logout</span>
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
