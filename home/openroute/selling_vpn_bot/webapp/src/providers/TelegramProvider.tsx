import React, { useEffect, useState } from 'react';

// We use the global window object for basic WebApp functionality
declare global {
  interface Window {
    Telegram?: any;
  }
}

export const TelegramContext = React.createContext<{
  user: any;
  isReady: boolean;
}>({ user: null, isReady: false });

export const TelegramProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isReady, setIsReady] = useState(false);
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (webApp) {
      webApp.ready();
      webApp.expand();
      
      const initDataUnsafe = webApp.initDataUnsafe;
      if (initDataUnsafe?.user) {
        setUser(initDataUnsafe.user);
      }
      setIsReady(true);
    } else {
      // Fallback for browser testing without Telegram
      console.warn("Telegram WebApp not detected. Running in standalone mode.");
      setIsReady(true);
      setUser({ id: 123456789, first_name: "Admin Tester" }); // Mock user
    }
  }, []);

  if (!isReady) {
    return <div className="min-h-screen flex items-center justify-center tg-bg tg-text">در حال اتصال به تلگرام...</div>;
  }

  return (
    <TelegramContext.Provider value={{ user, isReady }}>
      {children}
    </TelegramContext.Provider>
  );
};
