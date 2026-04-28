/** API Service - 統一封裝所有 API 呼叫，簡潔直接 */
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 客戶資料
export const getCustomers = (search) => 
  api.get('/customers', { params: { search } }).then(res => res.data)

export const getCustomer = (customerCode) => 
  api.get(`/customers/${customerCode}`).then(res => res.data)

export const createCustomer = (data) => 
  api.post('/customers', data).then(res => res.data)

export const updateCustomer = (customerCode, data) => 
  api.put(`/customers/${customerCode}`, data).then(res => res.data)

export const deleteCustomer = (customerCode) => 
  api.delete(`/customers/${customerCode}`)

export const changeCustomerCode = (customerCode, newCode) =>
  api.post(`/customers/${customerCode}/change-code`, { new_customer_code: newCode }).then(res => res.data)

// 公司資料
export const getCompanies = (type, search) => 
  api.get('/companies', { params: { type, search } }).then(res => res.data)

export const getCompany = (companyCode) => 
  api.get(`/companies/${companyCode}`).then(res => res.data)

export const createCompany = (data) => 
  api.post('/companies', data).then(res => res.data)

export const updateCompany = (companyCode, data) => 
  api.put(`/companies/${companyCode}`, data).then(res => res.data)

export const deleteCompany = (companyCode) => 
  api.delete(`/companies/${companyCode}`)

// 合約資料
export const getLeasingContracts = (search, accountingPeriod = 'current') =>
  api.get('/contracts/leasing', { params: { search, accounting_period: accountingPeriod } }).then(res => res.data)

export const getBuyoutContracts = (search, accountingPeriod = 'current') =>
  api.get('/contracts/buyout', { params: { search, accounting_period: accountingPeriod } }).then(res => res.data)

export const createLeasingContract = (data) => 
  api.post('/contracts/leasing', data).then(res => res.data)

export const createBuyoutContract = (data) => 
  api.post('/contracts/buyout', data).then(res => res.data)

export const updateLeasingContract = (contractCode, data) => 
  api.put(`/contracts/leasing/${contractCode}`, data).then(res => res.data)

export const updateBuyoutContract = (contractCode, data) => 
  api.put(`/contracts/buyout/${contractCode}`, data).then(res => res.data)

export const deleteLeasingContract = (contractCode) => 
  api.delete(`/contracts/leasing/${contractCode}`)

export const deleteBuyoutContract = (contractCode) => 
  api.delete(`/contracts/buyout/${contractCode}`)

export const pauseLeasingContract = (contractCode) =>
  api.post(`/contracts/leasing/${contractCode}/pause`).then(res => res.data)

export const resumeLeasingContract = (contractCode, data = {}) =>
  api.post(`/contracts/leasing/${contractCode}/resume`, data).then(res => res.data)

export const pauseBuyoutContract = (contractCode) =>
  api.post(`/contracts/buyout/${contractCode}/pause`).then(res => res.data)

export const resumeBuyoutContract = (contractCode, data = {}) =>
  api.post(`/contracts/buyout/${contractCode}/resume`, data).then(res => res.data)

// 帳款資料
export const getReceivables = (filters = {}) => 
  api.get('/accounts/receivables', { params: filters }).then(res => res.data)

export const updateReceivableAmount = (arType, id, data) =>
  api.put(`/accounts/receivables/${arType}/${id}/amount`, data).then(res => res.data)

export const getUnpaidPayables = (filters = {}) => 
  api.get('/accounts/payables/unpaid', { params: filters }).then(res => res.data)

export const getPaidPayables = (filters = {}) => 
  api.get('/accounts/payables/paid', { params: filters }).then(res => res.data)

export const getServiceExpenses = (filters = {}) => 
  api.get('/accounts/service', { params: filters }).then(res => res.data)

export const updateServiceExpenseAmount = (id, data) =>
  api.put(`/accounts/service/${id}/amount`, data).then(res => res.data)

export const createExtraExpense = (data) =>
  api.post('/accounts/service/extra', data).then(res => res.data)

export const updateExtraExpense = (id, data) =>
  api.put(`/accounts/service/extra/${id}`, data).then(res => res.data)

export const deleteExtraExpense = (id) =>
  api.delete(`/accounts/service/extra/${id}`)

// 銀行帳本
export const getBankLedger = (fromDate, toDate, search, accountingPeriod = 'current') =>
  api.get('/bank-ledger', { params: { from_date: fromDate, to_date: toDate, search, accounting_period: accountingPeriod } }).then(res => res.data)

export const createBankLedger = (data) => 
  api.post('/bank-ledger', data).then(res => res.data)

export const updateBankLedger = (id, data) => 
  api.put(`/bank-ledger/${id}`, data).then(res => res.data)

export const deleteBankLedger = (id) => 
  api.delete(`/bank-ledger/${id}`)

// 對帳相關
export const getReconcilableReceivables = (search, type, accountingPeriod = 'current') =>
  api.get('/bank-ledger/reconcilable/receivables', { params: { search, type, accounting_period: accountingPeriod } }).then(res => res.data)

export const getReconcilableServiceExpenses = (search, service_type, accountingPeriod = 'current') =>
  api.get('/bank-ledger/reconcilable/service-expenses', { params: { search, service_type, accounting_period: accountingPeriod } }).then(res => res.data)

export const reconcileBankLedger = (id, data) => 
  api.post(`/bank-ledger/${id}/reconcile`, data).then(res => res.data)

export const unreconcileBankLedger = (id, revert = true) => 
  api.post(`/bank-ledger/${id}/unreconcile?revert=${revert}`).then(res => res.data)

export default api

