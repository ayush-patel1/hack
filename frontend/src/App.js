import React, { useState } from 'react';
import { useUser } from '@clerk/clerk-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Dashboard from './pages/Dashboard';
import PlotComparison from './pages/PlotComparison';
import PlotAnalysis from './pages/PlotAnalysis';
import ViolationTable from './pages/ViolationTable';
import Charts from './pages/Charts';
import ExportPage from './pages/ExportPage';
import SignInPage from './pages/SignInPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30000, retry: 1 } },
});

const PAGES = [
  { id: 'dashboard', label: 'Dashboard', icon: 'LayoutDashboard' },
  { id: 'plot-comparison', label: 'Plot Comparison', icon: 'GitCompare' },
  { id: 'analysis', label: 'Plot Analysis', icon: 'Microscope' },
  { id: 'table', label: 'Violations Table', icon: 'Table2' },
  { id: 'charts', label: 'Analytics', icon: 'BarChart3' },
  { id: 'export', label: 'Export & Reports', icon: 'Download' },
];

function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const { isSignedIn, isLoaded } = useUser();

  if (!isLoaded) {
    return (
      <div className="auth-loading">
        <div className="auth-spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  if (!isSignedIn) {
    return <SignInPage />;
  }

  const renderPage = () => {
    switch (activePage) {
      case 'dashboard': return <Dashboard />;
      case 'plot-comparison': return <PlotComparison />;
      case 'analysis': return <PlotAnalysis />;
      case 'table': return <ViolationTable />;
      case 'charts': return <Charts />;
      case 'export': return <ExportPage />;
      default: return <Dashboard />;
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <div className="app-layout">
        <Sidebar pages={PAGES} active={activePage} onNavigate={setActivePage} />
        <main className="main-content">
          <Header />
          {renderPage()}
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;

