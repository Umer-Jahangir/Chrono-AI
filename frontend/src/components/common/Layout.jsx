import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Header from './Header';
import MobileNavDrawer from './MobileNavDrawer';

export default function Layout() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  return (
    <div className="flex min-h-dvh w-full min-w-0 flex-col overflow-x-hidden bg-[#f4f2ee] font-body-md text-on-surface">
      <Header onToggleDrawer={() => setIsDrawerOpen(true)} />
      <MobileNavDrawer isOpen={isDrawerOpen} onClose={() => setIsDrawerOpen(false)} />
      
      {/* pt-16 ensures content starts below the header */}
      <div className="relative flex min-h-dvh w-full min-w-0 flex-1 flex-col pt-16">
        <Outlet />
      </div>
    </div>
  );
}
