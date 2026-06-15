import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Agente1 from './pages/Agente1'
import Agente2 from './pages/Agente2'
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
          <Route path="/agente1" element={<Agente1 />} />
          <Route path="/agente2" element={<Agente2 />} />
          <Route path="/clientes" element={<Clientes />} />
          <Route path="/imoveis" element={<Imoveis />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/config" element={<Config />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
