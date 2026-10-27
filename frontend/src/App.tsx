import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import CaseSearch from './pages/CaseSearch'
import DraftGenerator from './pages/DraftGenerator'

const tab = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
    isActive ? 'bg-white/15 text-white' : 'text-blue-100 hover:bg-white/10 hover:text-white'
  }`

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="bg-ink text-white shadow">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">⚖️</span>
            <div>
              <div className="text-lg font-bold leading-tight">VakeelAI</div>
              <div className="text-xs text-blue-200">eCourts case lookup · Legal draft generator</div>
            </div>
          </div>
          <nav className="flex gap-1">
            <NavLink to="/cases" className={tab}>
              Case Search
            </NavLink>
            <NavLink to="/drafts" className={tab}>
              Draft Generator
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/cases" replace />} />
          <Route path="/cases" element={<CaseSearch />} />
          <Route path="/drafts" element={<DraftGenerator />} />
          <Route path="*" element={<Navigate to="/cases" replace />} />
        </Routes>
      </main>

      <footer className="py-4 text-center text-xs text-slate-400">
        Data fetched live from services.ecourts.gov.in · Drafts are templates and must be reviewed by an advocate before filing.
      </footer>
    </div>
  )
}
