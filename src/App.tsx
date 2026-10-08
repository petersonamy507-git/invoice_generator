import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { PayrollProvider } from './context/PayrollContext'
import { ThemeProvider } from './context/ThemeContext'
import { AuthPage } from './pages/AuthPage'
import { InvoicePage } from './pages/InvoicePage'
import { TeamPage } from './pages/TeamPage'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PayrollProvider>
          <Routes>
            <Route path="/signin" element={<AuthPage />} />
            <Route path="/signup" element={<Navigate to="/signin" replace />} />
            <Route path="/" element={<InvoicePage />} />
            <Route path="/team" element={<TeamPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </PayrollProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
