import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import './index.css'
import Daily from './pages/Daily'
import Trends from './pages/Trends'
import Ideas from './pages/Ideas'
import Favourites from './pages/Favourites'
import IdeaDetail from './pages/IdeaDetail'
import ClusterDetail from './pages/ClusterDetail'
import Run from './pages/Run'

function Layout() {
  const link = "px-4 py-2 rounded-lg text-sm font-medium transition-colors"
  const active = "bg-white text-gray-900 shadow-sm"
  const inactive = "text-gray-400 hover:text-white"

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
        <span className="text-lg font-bold text-white">Reddit Miner</span>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          <NavLink to="/" end className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>Daily</NavLink>
          <NavLink to="/trends" className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>Trends</NavLink>
          <NavLink to="/ideas" className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>Ideas</NavLink>
          <NavLink to="/favourites" className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>★</NavLink>
          <NavLink to="/run" className={({ isActive }) => `${link} ${isActive ? active : inactive}`}>Run</NavLink>
        </div>
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<Daily />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/ideas" element={<Ideas />} />
          <Route path="/favourites" element={<Favourites />} />
          <Route path="/ideas/:id" element={<IdeaDetail />} />
          <Route path="/clusters/:id" element={<ClusterDetail />} />
          <Route path="/run" element={<Run />} />
          <Route path="/run/:runId" element={<Run />} />
        </Routes>
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  </StrictMode>,
)
