import { useEffect } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError, startWarmUp } from '@/api/client';
import { AuthProvider } from '@/auth';
import { ToastProvider } from '@/components/ui/Toast';
import { AppRoutes } from './routes';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      // The API client already retries idempotent GETs once; do not stack more retries on 4xx.
      retry: (count, err) => !(err instanceof ApiError && err.status > 0 && err.status < 500) && count < 1,
    },
  },
});

export default function App() {
  // /health warm-up drives the cold-start banner (Render free tier sleeps).
  useEffect(() => startWarmUp(), []);
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
