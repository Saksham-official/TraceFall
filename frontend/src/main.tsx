import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import { ApiError } from './api/client'
import { AuthProvider } from './auth'
import { ErrorBoundary } from './components/ErrorBoundary'
import { applyTheme, readTheme } from './lib/theme'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 401 is handled by the client's refresh-then-expire path; retrying it is noise.
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
})

// Before first paint, so a dark preference never flashes light.
applyTheme(readTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
