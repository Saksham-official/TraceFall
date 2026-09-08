import { Link, Route, Routes } from 'react-router-dom'

import { RequireAuth } from './auth'
import { AppShell } from './components/AppShell'
import { ArrowLeftIcon, SearchIcon } from './components/icons'
import { EmptyState, Button } from './components/ui'
import { AddressIntakePage } from './pages/AddressIntakePage'
import { AnalysisProgressPage } from './pages/AnalysisProgressPage'
import { CaseDetailPage } from './pages/CaseDetailPage'
import { DashboardPage } from './pages/DashboardPage'
import { InvestigationPage } from './pages/InvestigationPage'
import { LoginPage } from './pages/LoginPage'
import { NewCasePage } from './pages/NewCasePage'
import { WelcomePage } from './pages/WelcomePage'

export function App() {
  return (
    <Routes>
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="cases/new" element={<NewCasePage />} />
        <Route path="cases/:caseId" element={<CaseDetailPage />} />
        <Route path="cases/:caseId/address" element={<AddressIntakePage />} />
        <Route path="analyses/:runId" element={<AnalysisProgressPage />} />
        <Route path="analyses/:runId/investigation" element={<InvestigationPage />} />
        <Route
          path="*"
          element={
            <div className="mx-auto max-w-lg pt-10">
              <EmptyState
                title="Page not found"
                icon={<SearchIcon />}
                action={
                  <Link to="/">
                    <Button icon={<ArrowLeftIcon />}>Back to cases</Button>
                  </Link>
                }
              >
                <p>The address may be mistyped, or the case or analysis it pointed at no longer exists.</p>
              </EmptyState>
            </div>
          }
        />
      </Route>
    </Routes>
  )
}
