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
export const getLeasingContracts = (search) => 
  api.get('/contracts/leasing', { params: { search } }).then(res => res.data)

export const getBuyoutContracts = (search) => 
  api.get('/contracts/buyout', { params: { search } }).then(res => res.data)

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

// 帳款資料
export const getReceivables = (fromDate, toDate) => 
  api.get('/accounts/receivables', { params: { from_date: fromDate, to_date: toDate } }).then(res => res.data)

export const getUnpaidPayables = (fromDate, toDate) => 
  api.get('/accounts/payables/unpaid', { params: { from_date: fromDate, to_date: toDate } }).then(res => res.data)

export const getPaidPayables = (fromDate, toDate) => 
  api.get('/accounts/payables/paid', { params: { from_date: fromDate, to_date: toDate } }).then(res => res.data)

export const getServiceExpenses = (fromDate, toDate) => 
  api.get('/accounts/service', { params: { from_date: fromDate, to_date: toDate } }).then(res => res.data)

// 銀行帳本
export const getBankLedger = (fromDate, toDate, search) => 
  api.get('/bank-ledger', { params: { from_date: fromDate, to_date: toDate, search } }).then(res => res.data)

export const createBankLedger = (data) => 
  api.post('/bank-ledger', data).then(res => res.data)

export const updateBankLedger = (id, data) => 
  api.put(`/bank-ledger/${id}`, data).then(res => res.data)

export const deleteBankLedger = (id) => 
  api.delete(`/bank-ledger/${id}`)

export default api

