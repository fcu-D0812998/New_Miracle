import { BrowserRouter, Routes, Route } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Dashboard from './pages/Dashboard'
import Customers from './pages/Customers'
import Companies from './pages/Companies'
import Contracts from './pages/Contracts'
import Accounts from './pages/Accounts'
import BankLedger from './pages/BankLedger'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="customers" element={<Customers />} />
          <Route path="companies" element={<Companies />} />
          <Route path="contracts" element={<Contracts />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="bank-ledger" element={<BankLedger />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App



