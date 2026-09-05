import { Link, Route, Routes } from 'react-router-dom'

import { RequireAuth } from './auth'
import { AppShell } from './components/AppShell'
import { EmptyState, Button } from './components/ui'
import { AddressIntakePage } from './pages/AddressIntakePage'
import { AnalysisProgressPage } from './pages/AnalysisProgressPage'
import { CaseDetailPage } from './pages/CaseDetailPage'
import { DashboardPage } from './pages/DashboardPage'
import { InvestigationPage } from './pages/InvestigationPage'
import { LoginPage } from './pages/LoginPage'
import { NewCasePage } from './pages/NewCasePage'

export function App() {
  return (
    <Routes>
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
            <EmptyState
              title="Page not found"
              action={
                <Link to="/">
                  <Button>Back to cases</Button>
                </Link>
              }
            />
          }
        />
      </Route>
    </Routes>
  )
}
