import React, { useContext, useEffect, useState } from 'react';
import { TelegramProvider, TelegramContext } from './providers/TelegramProvider';
import { ClientDashboard } from './views/ClientDashboard';
import { AdminManagement } from './views/AdminManagement';
import { apiClient } from './api/client';

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: any }> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("ErrorBoundary caught an error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-100 text-red-800 min-h-screen font-mono text-xs overflow-auto">
          <h1 className="text-lg font-bold mb-2">Internal App Error</h1>
          <p className="font-bold mb-2">{this.state.error?.toString()}</p>
          <pre className="whitespace-pre-wrap">{this.state.error?.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const AppContent: React.FC = () => {
  const { isReady } = useContext(TelegramContext);
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  
  useEffect(() => {
    if (isReady) {
      const checkRole = async () => {
        try {
          await apiClient.get('/admin/webapp/stats');
          setIsAdmin(true);
        } catch (err: any) {
          setIsAdmin(false);
        }
      };
      checkRole();
    }
  }, [isReady]);

  if (!isReady || isAdmin === null) {
    return <div className="min-h-screen flex items-center justify-center tg-bg tg-text font-vazir">در حال تایید هویت...</div>;
  }

  return (
    <div className="w-full min-h-screen">
      {isAdmin ? <AdminManagement /> : <ClientDashboard />}
    </div>
  );
};

function App() {
  return (
    <ErrorBoundary>
      <TelegramProvider>
        <AppContent />
      </TelegramProvider>
    </ErrorBoundary>
  );
}

export default App;
