import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import AgenteConfig from './pages/AgenteConfig'
import Chat from './pages/Chat'
import Clientes from './pages/Clientes'
import Imoveis from './pages/Imoveis'
import Leads from './pages/Leads'
import Config from './pages/Config'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/agentes/:agente" element={<AgenteConfig />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/clientes" element={<Clientes />} />
          <Route path="/imoveis" element={<Imoveis />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/config" element={<Config />} />
          {/* Rotas antigas — links guardados continuam a funcionar. */}
          <Route path="/agente1" element={<Navigate to="/agentes/voz" replace />} />
          <Route path="/agente2" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
