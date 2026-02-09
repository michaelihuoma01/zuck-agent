import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/layout/Layout'
import MobileBottomNav from './components/layout/MobileBottomNav'
import ErrorBoundary from './components/common/ErrorBoundary'
import { ToastProvider } from './components/common/Toast'
import Dashboard from './pages/Dashboard'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import ExternalSessionPage from './pages/ExternalSessionPage'
import SessionPage from './pages/SessionPage'
import SettingsPage from './pages/SettingsPage'
import InstallPrompt from './components/pwa/InstallPrompt'
import { ApiError } from './api/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry 4xx client errors (except 408 timeout and 429 rate limit)
        if (error instanceof ApiError) {
          if (error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) {
            return false
          }
        }
        return failureCount < 2
      },
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: false,
    },
  },
})

function HideableBottomNav() {
  const { pathname } = useLocation()
  // Hide bottom nav on full-screen session pages
  if (pathname.startsWith('/sessions/')) return null
  if (/\/projects\/[^/]+\/external-sessions\//.test(pathname)) return null
  return <MobileBottomNav />
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              {/* Full-screen session views — no Layout shell */}
              <Route path="/sessions/:id" element={<SessionPage />} />
              <Route path="/projects/:projectId/external-sessions/:sessionId" element={<ExternalSessionPage />} />

              {/* Standard pages with sidebar + header */}
              <Route element={<Layout />}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/projects" element={<ProjectsPage />} />
                <Route path="/projects/:id" element={<ProjectDetailPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
            </Routes>
            <HideableBottomNav />
          </BrowserRouter>
          <InstallPrompt />
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
