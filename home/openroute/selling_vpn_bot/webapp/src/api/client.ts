import axios from 'axios';

const getBaseUrl = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
    return 'http://localhost:8000/api/v1';
  }
  return '/api/v1';
};

const API_BASE_URL = getBaseUrl();

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

// Interceptor to dynamically attach the Telegram Init Data to every request
apiClient.interceptors.request.use((config) => {
  // We extract the init data from the Telegram window object
  const initData = window.Telegram?.WebApp?.initData;
  if (initData) {
    config.headers['Telegram-Web-App-Data'] = initData;
  }
  return config;
});
