import { useEffect, useMemo, useState } from 'react'
import {
  Tabs,
  Table,
  DatePicker,
  Space,
  Button,
  Input,
  Select,
  Form,
  Modal,
  InputNumber,
  message,
  Tag,
  Popconfirm
} from 'antd'
import { DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'
import {
  getReceivables,
  updateReceivableAmount,
  getUnpaidPayables,
  getPaidPayables,
  getServiceExpenses,
  updateServiceExpenseAmount,
  createExtraExpense,
  updateExtraExpense,
  deleteExtraExpense
} from '../services/api'
import { dateSorter, numberSorter, statusSorter, textSorter } from '../utils/tableSorters'

const { RangePicker } = DatePicker
const DEFAULT_ACCOUNTING_FILTERS = { accounting_period: 'current' }
const ACCOUNTING_PERIOD_OPTIONS = [
  { value: 'current', label: '本期' },
  { value: 'prior', label: '前帳' },
  { value: 'all', label: '全部' }
]
const RECEIVABLE_STATUS_ORDER = { 未收: 0, 部分收款: 1, 已收款: 2 }
const PAYABLE_STATUS_ORDER = { 未付款: 0, 部分付款: 1, 已付款: 2 }

const ReceivablesSearchForm = ({ onSearch }) => {
  const [form] = Form.useForm()

  const handleSearch = () => {
    const values = form.getFieldsValue()
    const filters = {}
    if (values.contract_code) filters.contract_code = values.contract_code
    if (values.customer_code) filters.customer_code = values.customer_code
    if (values.customer_name) filters.customer_name = values.customer_name
    if (values.dateRange?.[0]) filters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange?.[1]) filters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) filters.payment_status = values.payment_status
    if (values.type) filters.type = values.type
    filters.accounting_period = values.accounting_period || DEFAULT_ACCOUNTING_FILTERS.accounting_period
    onSearch(filters)
  }

  return (
    <Form form={form} layout="inline" initialValues={DEFAULT_ACCOUNTING_FILTERS} style={{ marginBottom: 16 }}>
      <Form.Item label="合約編號" name="contract_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶代碼" name="customer_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="日期範圍" name="dateRange">
        <RangePicker format="YYYY-MM-DD" />
      </Form.Item>
      <Form.Item label="類型" name="type">
        <Select placeholder="全部" style={{ width: 100 }} allowClear>
          <Select.Option value="租賃">租賃</Select.Option>
          <Select.Option value="買斷">買斷</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="繳費狀況" name="payment_status">
        <Select placeholder="全部" style={{ width: 120 }} allowClear>
          <Select.Option value="未收">未收</Select.Option>
          <Select.Option value="部分收款">部分收款</Select.Option>
          <Select.Option value="已收款">已收款</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="帳務期間" name="accounting_period">
        <Select style={{ width: 110 }} options={ACCOUNTING_PERIOD_OPTIONS} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch(DEFAULT_ACCOUNTING_FILTERS) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

const PayablesSearchForm = ({ onSearch }) => {
  const [form] = Form.useForm()

  const handleSearch = () => {
    const values = form.getFieldsValue()
    const filters = {}
    if (values.contract_code) filters.contract_code = values.contract_code
    if (values.customer_code) filters.customer_code = values.customer_code
    if (values.customer_name) filters.customer_name = values.customer_name
    if (values.dateRange?.[0]) filters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange?.[1]) filters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) filters.payment_status = values.payment_status
    if (values.payable_type) filters.payable_type = values.payable_type
    if (values.contract_type) filters.contract_type = values.contract_type
    filters.accounting_period = values.accounting_period || DEFAULT_ACCOUNTING_FILTERS.accounting_period
    onSearch(filters)
  }

  return (
    <Form form={form} layout="inline" initialValues={DEFAULT_ACCOUNTING_FILTERS} style={{ marginBottom: 16 }}>
      <Form.Item label="合約編號" name="contract_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶代碼" name="customer_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="日期範圍" name="dateRange">
        <RangePicker format="YYYY-MM-DD" />
      </Form.Item>
      <Form.Item label="應付類型" name="payable_type">
        <Select placeholder="全部" style={{ width: 130 }} allowClear>
          <Select.Option value="業務">業務</Select.Option>
          <Select.Option value="維護">維護</Select.Option>
          <Select.Option value="額外開銷">額外開銷</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="合約類型" name="contract_type">
        <Select placeholder="全部" style={{ width: 130 }} allowClear>
          <Select.Option value="租賃">租賃</Select.Option>
          <Select.Option value="買斷">買斷</Select.Option>
          <Select.Option value="額外開銷">額外開銷</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="付款狀況" name="payment_status">
        <Select placeholder="全部" style={{ width: 120 }} allowClear>
          <Select.Option value="未付款">未付款</Select.Option>
          <Select.Option value="部分付款">部分付款</Select.Option>
          <Select.Option value="已付款">已付款</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="帳務期間" name="accounting_period">
        <Select style={{ width: 110 }} options={ACCOUNTING_PERIOD_OPTIONS} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch(DEFAULT_ACCOUNTING_FILTERS) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

const ServiceSearchForm = ({ onSearch }) => {
  const [form] = Form.useForm()

  const handleSearch = () => {
    const values = form.getFieldsValue()
    const filters = {}
    if (values.contract_code) filters.contract_code = values.contract_code
    if (values.customer_code) filters.customer_code = values.customer_code
    if (values.customer_name) filters.customer_name = values.customer_name
    if (values.dateRange?.[0]) filters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange?.[1]) filters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) filters.payment_status = values.payment_status
    if (values.service_type) filters.service_type = values.service_type
    filters.accounting_period = values.accounting_period || DEFAULT_ACCOUNTING_FILTERS.accounting_period
    onSearch(filters)
  }

  return (
    <Form form={form} layout="inline" initialValues={DEFAULT_ACCOUNTING_FILTERS} style={{ marginBottom: 16 }}>
      <Form.Item label="合約編號" name="contract_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶代碼" name="customer_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="日期範圍" name="dateRange">
        <RangePicker format="YYYY-MM-DD" />
      </Form.Item>
      <Form.Item label="服務類型" name="service_type">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="付款狀況" name="payment_status">
        <Select placeholder="全部" style={{ width: 120 }} allowClear>
          <Select.Option value="未付款">未付款</Select.Option>
          <Select.Option value="部分付款">部分付款</Select.Option>
          <Select.Option value="已付款">已付款</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="帳務期間" name="accounting_period">
        <Select style={{ width: 110 }} options={ACCOUNTING_PERIOD_OPTIONS} />
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch(DEFAULT_ACCOUNTING_FILTERS) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

const formatMoney = (value) => `NT$ ${Number(value || 0).toLocaleString()}`

function Accounts() {
  const [activeTab, setActiveTab] = useState('receivables')
  const [receivablesData, setReceivablesData] = useState([])
  const [unpaidPayableData, setUnpaidPayableData] = useState([])
  const [paidPayableData, setPaidPayableData] = useState([])
  const [serviceExpenseData, setServiceExpenseData] = useState([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [receivablesFilters, setReceivablesFilters] = useState(DEFAULT_ACCOUNTING_FILTERS)
  const [payablesFilters, setPayablesFilters] = useState(DEFAULT_ACCOUNTING_FILTERS)
  const [serviceFilters, setServiceFilters] = useState(DEFAULT_ACCOUNTING_FILTERS)
  const [isAmountModalOpen, setIsAmountModalOpen] = useState(false)
  const [editingAmountTarget, setEditingAmountTarget] = useState(null)
  const [isExtraExpenseModalOpen, setIsExtraExpenseModalOpen] = useState(false)
  const [editingExtraExpense, setEditingExtraExpense] = useState(null)
  const [amountForm] = Form.useForm()
  const [extraExpenseForm] = Form.useForm()

  const currentExportMeta = useMemo(() => ({
    receivables: { fileName: '應收帳款', sheetName: '應收帳款', data: receivablesData },
    'unpaid-payable': { fileName: '未出帳款', sheetName: '未出帳款', data: unpaidPayableData },
    'paid-payable': { fileName: '已出帳款', sheetName: '已出帳款', data: paidPayableData },
    service: { fileName: '服務費用', sheetName: '服務費用', data: serviceExpenseData }
  }), [receivablesData, unpaidPayableData, paidPayableData, serviceExpenseData])

  const loadCurrentTab = async () => {
    setLoading(true)
    try {
      if (activeTab === 'receivables') {
        setReceivablesData(await getReceivables(receivablesFilters))
      } else if (activeTab === 'unpaid-payable') {
        setUnpaidPayableData(await getUnpaidPayables(payablesFilters))
      } else if (activeTab === 'paid-payable') {
        setPaidPayableData(await getPaidPayables(payablesFilters))
      } else if (activeTab === 'service') {
        setServiceExpenseData(await getServiceExpenses(serviceFilters))
      }
    } catch (error) {
      message.error('載入資料失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCurrentTab()
  }, [activeTab, receivablesFilters, payablesFilters, serviceFilters])

  const renderAdjustedAmount = (_, record) => {
    const hasAdjustment = record.adjusted_amount !== null && record.adjusted_amount !== undefined
    return (
      <div>
        <div>{formatMoney(record.amount)}</div>
        {hasAdjustment && (
          <div style={{ fontSize: 12, color: '#666' }}>
            原始 {formatMoney(record.original_amount)} <Tag color="orange">已調整</Tag>
          </div>
        )}
      </div>
    )
  }

  const openAmountModal = (kind, record) => {
    setEditingAmountTarget({ kind, record })
    amountForm.setFieldsValue({ amount: record.amount })
    setIsAmountModalOpen(true)
  }

  const handleAmountSubmit = async () => {
    try {
      const values = await amountForm.validateFields()
      if (editingAmountTarget?.kind === 'receivable') {
        await updateReceivableAmount(editingAmountTarget.record.type, editingAmountTarget.record.id, values)
      } else {
        await updateServiceExpenseAmount(editingAmountTarget.record.id, values)
      }
      message.success('金額更新成功')
      setIsAmountModalOpen(false)
      setEditingAmountTarget(null)
      amountForm.resetFields()
      loadCurrentTab()
    } catch (error) {
      if (error.errorFields) return
      message.error('更新失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const openExtraExpenseModal = (record = null) => {
    setEditingExtraExpense(record)
    if (record) {
      extraExpenseForm.setFieldsValue({
        service_date: record.date ? dayjs(record.date) : dayjs(),
        expense_category: record.expense_category || record.payable_type || '額外開銷',
        description: record.description,
        amount: record.amount,
        contract_code: record.contract_code,
        vendor_name: record.vendor_name || record.company_code
      })
    } else {
      extraExpenseForm.resetFields()
    }
    setIsExtraExpenseModalOpen(true)
  }

  const handleExtraExpenseSubmit = async () => {
    try {
      const values = await extraExpenseForm.validateFields()
      const payload = {
        ...values,
        contract_code: values.contract_code || null,
        vendor_name: values.vendor_name || null,
        service_date: values.service_date.format('YYYY-MM-DD')
      }
      if (editingExtraExpense) {
        await updateExtraExpense(editingExtraExpense.id, payload)
        message.success('額外開銷已更新')
      } else {
        await createExtraExpense(payload)
        message.success('額外開銷已新增')
      }
      setIsExtraExpenseModalOpen(false)
      setEditingExtraExpense(null)
      extraExpenseForm.resetFields()
      if (activeTab === 'paid-payable') {
        setActiveTab('unpaid-payable')
      } else {
        loadCurrentTab()
      }
    } catch (error) {
      if (error.errorFields) return
      message.error((editingExtraExpense ? '更新' : '新增') + '失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleDeleteExtraExpense = async (record) => {
    try {
      await deleteExtraExpense(record.id)
      message.success('額外開銷已刪除')
      loadCurrentTab()
    } catch (error) {
      message.error('刪除失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleExportCurrentTab = () => {
    const meta = currentExportMeta[activeTab]
    if (!meta?.data?.length) {
      message.warning('目前頁籤沒有資料可匯出')
      return
    }

    setExporting(true)
    try {
      const exportRows = meta.data.map((item) => {
        if (activeTab === 'receivables') {
          return {
            類型: item.type,
            合約編號: item.contract_code,
            客戶代碼: item.customer_code,
            客戶名稱: item.customer_name,
            起日: item.date,
            迄日: item.end_date || '',
            原始金額: item.original_amount,
            最終金額: item.amount,
            手續費: item.fee,
            已收金額: item.received_amount,
            繳費狀況: item.payment_status
          }
        }

        if (activeTab === 'service') {
          return {
            合約編號: item.contract_code,
            客戶代碼: item.customer_code,
            客戶名稱: item.customer_name,
            服務日期: item.service_date || '',
            服務類型: item.service_type,
            公司代碼: item.repair_company_code || '',
            付款對象: item.payee_name || item.repair_company_code || '',
            原始金額: item.original_amount,
            最終金額: item.amount,
            已付金額: item.paid_amount,
            付款狀況: item.payment_status
          }
        }

        return {
          日期: item.date || '',
          合約編號: item.contract_code || '',
          合約類型: item.contract_type || '',
          客戶代碼: item.customer_code || '',
          客戶名稱: item.customer_name || '',
          應付類型: item.payable_type || '',
          付款對象: item.payee_name || item.company_code || '',
          公司代碼或廠商: item.company_code || '',
          說明: item.description || '',
          原始金額: item.original_amount,
          最終金額: item.amount,
          已付金額: item.paid_amount,
          未付金額: item.unpaid_amount,
          付款狀況: item.payment_status
        }
      })

      const workbook = XLSX.utils.book_new()
      const worksheet = XLSX.utils.json_to_sheet(exportRows)
      XLSX.utils.book_append_sheet(workbook, worksheet, meta.sheetName)
      XLSX.writeFile(workbook, `${meta.fileName}_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`)
      message.success('匯出成功')
    } catch (error) {
      message.error('匯出失敗：' + (error.message || '無法建立 Excel'))
    } finally {
      setExporting(false)
    }
  }

  const receivablesColumns = [
    { title: '類型', dataIndex: 'type', key: 'type', width: 80, sorter: textSorter('type') },
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code') },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120, sorter: textSorter('customer_code') },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150, sorter: textSorter('customer_name') },
    { title: '起日', dataIndex: 'date', key: 'date', width: 110, sorter: dateSorter('date') },
    { title: '迄日', dataIndex: 'end_date', key: 'end_date', width: 110, sorter: dateSorter('end_date'), render: (value) => value || '-' },
    { title: '金額', key: 'amount', width: 180, sorter: numberSorter('amount'), render: renderAdjustedAmount },
    { title: '手續費', dataIndex: 'fee', key: 'fee', width: 120, sorter: numberSorter('fee'), render: (value) => formatMoney(value) },
    { title: '已收金額', dataIndex: 'received_amount', key: 'received_amount', width: 120, sorter: numberSorter('received_amount'), render: (value) => formatMoney(value) },
    { title: '繳費狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120, sorter: statusSorter('payment_status', RECEIVABLE_STATUS_ORDER) },
    {
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openAmountModal('receivable', record)}>
          編輯金額
        </Button>
      )
    }
  ]

  const payableColumns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 110, sorter: dateSorter('date'), render: (value) => value || '-' },
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code'), render: (value) => value || '-' },
    { title: '合約類型', dataIndex: 'contract_type', key: 'contract_type', width: 110, sorter: textSorter('contract_type'), render: (value) => value || '-' },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150, sorter: textSorter('customer_name'), render: (value) => value || '-' },
    { title: '應付類型', dataIndex: 'payable_type', key: 'payable_type', width: 130, sorter: textSorter('payable_type') },
    {
      title: '付款對象',
      dataIndex: 'payee_name',
      key: 'payee_name',
      width: 180,
      sorter: textSorter((record) => record.payee_name || record.company_code),
      render: (value, record) => (
        <div>
          <div>{value || record.company_code || '-'}</div>
          {record.company_code && value && record.company_code !== value && (
            <div style={{ fontSize: 12, color: '#666' }}>{record.company_code}</div>
          )}
        </div>
      )
    },
    { title: '說明', dataIndex: 'description', key: 'description', width: 220, sorter: textSorter('description'), render: (value) => value || '-' },
    { title: '金額', key: 'amount', width: 180, sorter: numberSorter('amount'), render: renderAdjustedAmount },
    { title: '已付金額', dataIndex: 'paid_amount', key: 'paid_amount', width: 120, sorter: numberSorter('paid_amount'), render: (value) => formatMoney(value) },
    { title: '未付金額', dataIndex: 'unpaid_amount', key: 'unpaid_amount', width: 120, sorter: numberSorter('unpaid_amount'), render: (value) => formatMoney(value) },
    { title: '付款狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120, sorter: statusSorter('payment_status', PAYABLE_STATUS_ORDER) },
    ...(activeTab === 'unpaid-payable' ? [{
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right',
      render: (_, record) => (
        record.expense_source === 'extra' ? (
          <Space>
            <Button type="link" icon={<EditOutlined />} onClick={() => openExtraExpenseModal(record)}>
              編輯
            </Button>
            <Popconfirm
              title="確定要刪除這筆額外開銷嗎？"
              description="已付款或已對帳的額外開銷需要先取消對帳。"
              onConfirm={() => handleDeleteExtraExpense(record)}
            >
              <Button type="link" danger icon={<DeleteOutlined />}>刪除</Button>
            </Popconfirm>
          </Space>
        ) : (
          <Button type="link" icon={<EditOutlined />} onClick={() => openAmountModal('service', record)}>
            編輯金額
          </Button>
        )
      )
    }] : [])
  ]

  const serviceColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code') },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150, sorter: textSorter('customer_name') },
    { title: '服務日期', dataIndex: 'service_date', key: 'service_date', width: 110, sorter: dateSorter('service_date'), render: (value) => value || '-' },
    { title: '服務類型', dataIndex: 'service_type', key: 'service_type', width: 100, sorter: textSorter('service_type') },
    { title: '公司代碼', dataIndex: 'repair_company_code', key: 'repair_company_code', width: 140, sorter: textSorter('repair_company_code'), render: (value) => value || '-' },
    { title: '金額', key: 'amount', width: 180, sorter: numberSorter('amount'), render: renderAdjustedAmount },
    { title: '已付金額', dataIndex: 'paid_amount', key: 'paid_amount', width: 120, sorter: numberSorter('paid_amount'), render: (value) => formatMoney(value) },
    { title: '付款狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120, sorter: statusSorter('payment_status', PAYABLE_STATUS_ORDER) },
    {
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openAmountModal('service', record)}>
          編輯金額
        </Button>
      )
    }
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'flex-end' }}>
        {(activeTab === 'unpaid-payable' || activeTab === 'paid-payable') && (
          <Button icon={<PlusOutlined />} onClick={() => openExtraExpenseModal()}>
            新增額外開銷
          </Button>
        )}
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          onClick={handleExportCurrentTab}
          loading={exporting}
        >
          匯出目前頁籤
        </Button>
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'receivables',
            label: '應收帳款',
            children: (
              <>
                <ReceivablesSearchForm onSearch={setReceivablesFilters} />
                <Table columns={receivablesColumns} dataSource={receivablesData} rowKey="id" loading={loading} scroll={{ x: 1450 }} />
              </>
            )
          },
          {
            key: 'unpaid-payable',
            label: '未出帳款',
            children: (
              <>
                <PayablesSearchForm onSearch={setPayablesFilters} />
                <Table columns={payableColumns} dataSource={unpaidPayableData} rowKey="id" loading={loading} scroll={{ x: 1550 }} />
              </>
            )
          },
          {
            key: 'paid-payable',
            label: '已出帳款',
            children: (
              <>
                <PayablesSearchForm onSearch={setPayablesFilters} />
                <Table columns={payableColumns} dataSource={paidPayableData} rowKey="id" loading={loading} scroll={{ x: 1550 }} />
              </>
            )
          },
          {
            key: 'service',
            label: '服務費用',
            children: (
              <>
                <ServiceSearchForm onSearch={setServiceFilters} />
                <Table columns={serviceColumns} dataSource={serviceExpenseData} rowKey="id" loading={loading} scroll={{ x: 1300 }} />
              </>
            )
          }
        ]}
      />

      <Modal
        title={editingAmountTarget?.kind === 'receivable' ? '編輯應收金額' : '編輯服務費用金額'}
        open={isAmountModalOpen}
        onOk={handleAmountSubmit}
        onCancel={() => {
          setIsAmountModalOpen(false)
          setEditingAmountTarget(null)
          amountForm.resetFields()
        }}
        okText="儲存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={amountForm} layout="vertical">
          <Form.Item label="原始金額">
            <Input value={editingAmountTarget ? formatMoney(editingAmountTarget.record.original_amount) : ''} disabled />
          </Form.Item>
          <Form.Item
            label="最終金額"
            name="amount"
            rules={[{ required: true, message: '請輸入金額' }]}
          >
            <InputNumber min={0.01} step={100} style={{ width: '100%' }} addonBefore="NT$" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingExtraExpense ? '編輯額外開銷' : '新增額外開銷'}
        open={isExtraExpenseModalOpen}
        onOk={handleExtraExpenseSubmit}
        onCancel={() => {
          setIsExtraExpenseModalOpen(false)
          setEditingExtraExpense(null)
          extraExpenseForm.resetFields()
        }}
        okText={editingExtraExpense ? '儲存' : '新增'}
        cancelText="取消"
        destroyOnClose
      >
        <Form form={extraExpenseForm} layout="vertical">
          <Form.Item label="發生日" name="service_date" rules={[{ required: true, message: '請選擇日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="類別" name="expense_category">
            <Input placeholder="例如：安裝、搬運、耗材" />
          </Form.Item>
          <Form.Item label="內容" name="description" rules={[{ required: true, message: '請填寫內容' }]}>
            <Input.TextArea rows={3} placeholder="這次額外做了什麼" />
          </Form.Item>
          <Form.Item label="金額" name="amount" rules={[{ required: true, message: '請輸入金額' }]}>
            <InputNumber min={0.01} step={100} style={{ width: '100%' }} addonBefore="NT$" />
          </Form.Item>
          <Form.Item label="關聯合約" name="contract_code">
            <Input placeholder="可留空；若填寫會自動帶出客戶" />
          </Form.Item>
          <Form.Item label="對象 / 廠商" name="vendor_name">
            <Input placeholder="可留空" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Accounts
