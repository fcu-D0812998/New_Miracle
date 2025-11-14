import { useState, useEffect } from 'react'
import { 
  Tabs, 
  Table, 
  DatePicker, 
  Space, 
  Button, 
  Alert,
  Input,
  Select,
  Form,
  Row,
  Col
} from 'antd'
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'
import { getReceivables, getUnpaidPayables, getPaidPayables, getServiceExpenses } from '../services/api'

const { RangePicker } = DatePicker

const ReceivablesSearchForm = ({ filters, onSearch }) => {
  const [form] = Form.useForm()
  const handleSearch = () => {
    const values = form.getFieldsValue()
    const searchFilters = {}
    if (values.contract_code) searchFilters.contract_code = values.contract_code
    if (values.customer_code) searchFilters.customer_code = values.customer_code
    if (values.customer_name) searchFilters.customer_name = values.customer_name
    if (values.dateRange && values.dateRange[0]) searchFilters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange && values.dateRange[1]) searchFilters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) searchFilters.payment_status = values.payment_status
    if (values.type) searchFilters.type = values.type
    onSearch(searchFilters)
  }
  return (
    <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
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
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch({}) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

const PayablesSearchForm = ({ filters, onSearch }) => {
  const [form] = Form.useForm()
  const handleSearch = () => {
    const values = form.getFieldsValue()
    const searchFilters = {}
    if (values.contract_code) searchFilters.contract_code = values.contract_code
    if (values.customer_code) searchFilters.customer_code = values.customer_code
    if (values.customer_name) searchFilters.customer_name = values.customer_name
    if (values.dateRange && values.dateRange[0]) searchFilters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange && values.dateRange[1]) searchFilters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) searchFilters.payment_status = values.payment_status
    if (values.payable_type) searchFilters.payable_type = values.payable_type
    if (values.contract_type) searchFilters.contract_type = values.contract_type
    onSearch(searchFilters)
  }
  return (
    <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
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
      <Form.Item label="付款對象" name="payable_type">
        <Select placeholder="全部" style={{ width: 100 }} allowClear>
          <Select.Option value="業務">業務</Select.Option>
          <Select.Option value="維護">維護</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="合約類型" name="contract_type">
        <Select placeholder="全部" style={{ width: 100 }} allowClear>
          <Select.Option value="租賃">租賃</Select.Option>
          <Select.Option value="買斷">買斷</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item label="付款狀況" name="payment_status">
        <Select placeholder="全部" style={{ width: 120 }} allowClear>
          <Select.Option value="未付款">未付款</Select.Option>
          <Select.Option value="已付款">已付款</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch({}) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

const ServiceSearchForm = ({ filters, onSearch }) => {
  const [form] = Form.useForm()
  const handleSearch = () => {
    const values = form.getFieldsValue()
    const searchFilters = {}
    if (values.contract_code) searchFilters.contract_code = values.contract_code
    if (values.customer_code) searchFilters.customer_code = values.customer_code
    if (values.customer_name) searchFilters.customer_name = values.customer_name
    if (values.dateRange && values.dateRange[0]) searchFilters.from_date = values.dateRange[0].format('YYYY-MM-DD')
    if (values.dateRange && values.dateRange[1]) searchFilters.to_date = values.dateRange[1].format('YYYY-MM-DD')
    if (values.payment_status) searchFilters.payment_status = values.payment_status
    if (values.service_type) searchFilters.service_type = values.service_type
    onSearch(searchFilters)
  }
  return (
    <Form form={form} layout="inline" style={{ marginBottom: 16 }}>
      <Form.Item label="合約編號" name="contract_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶代碼" name="customer_code">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="服務日期範圍" name="dateRange">
        <RangePicker format="YYYY-MM-DD" />
      </Form.Item>
      <Form.Item label="服務類型" name="service_type">
        <Input placeholder="部分比對" style={{ width: 150 }} allowClear />
      </Form.Item>
      <Form.Item label="繳費狀況" name="payment_status">
        <Select placeholder="全部" style={{ width: 120 }} allowClear>
          <Select.Option value="未收">未收</Select.Option>
          <Select.Option value="部分收款">部分收款</Select.Option>
          <Select.Option value="已收款">已收款</Select.Option>
        </Select>
      </Form.Item>
      <Form.Item>
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查詢</Button>
      </Form.Item>
      <Form.Item>
        <Button onClick={() => { form.resetFields(); onSearch({}) }}>清除</Button>
      </Form.Item>
    </Form>
  )
}

function Accounts() {
  const [activeTab, setActiveTab] = useState('receivables')
  const [receivablesData, setReceivablesData] = useState([])
  const [unpaidPayableData, setUnpaidPayableData] = useState([])
  const [paidPayableData, setPaidPayableData] = useState([])
  const [serviceExpenseData, setServiceExpenseData] = useState([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [alertMessage, setAlertMessage] = useState(null)
  const [alertType, setAlertType] = useState('info')
  
  // 搜尋條件
  const [receivablesFilters, setReceivablesFilters] = useState({})
  const [payablesFilters, setPayablesFilters] = useState({})
  const [serviceFilters, setServiceFilters] = useState({})

  const loadReceivables = async () => {
    setLoading(true)
    try {
      const data = await getReceivables(receivablesFilters)
      setReceivablesData(data || [])
    } catch (error) {
      console.error('載入總應收帳款失敗', error)
      setReceivablesData([])
    } finally {
      setLoading(false)
    }
  }

  const loadUnpaidPayables = async () => {
    setLoading(true)
    try {
      const data = await getUnpaidPayables(payablesFilters)
      setUnpaidPayableData(data || [])
    } catch (error) {
      console.error('載入未出帳款失敗', error)
      setUnpaidPayableData([])
    } finally {
      setLoading(false)
    }
  }

  const loadPaidPayables = async () => {
    setLoading(true)
    try {
      const data = await getPaidPayables(payablesFilters)
      setPaidPayableData(data || [])
    } catch (error) {
      console.error('載入已出帳款失敗', error)
      setPaidPayableData([])
    } finally {
      setLoading(false)
    }
  }

  const loadServiceExpenses = async () => {
    setLoading(true)
    try {
      const data = await getServiceExpenses(serviceFilters)
      setServiceExpenseData(data || [])
    } catch (error) {
      console.error('載入服務費用失敗', error)
      setServiceExpenseData([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'receivables') {
      loadReceivables()
    }
  }, [activeTab, receivablesFilters])

  useEffect(() => {
    if (activeTab === 'unpaid-payable') {
      loadUnpaidPayables()
    } else if (activeTab === 'paid-payable') {
      loadPaidPayables()
    }
  }, [activeTab, payablesFilters])

  useEffect(() => {
    if (activeTab === 'service') {
      loadServiceExpenses()
    }
  }, [activeTab, serviceFilters])

  useEffect(() => {
    loadReceivables()
  }, [])

  const receivablesColumns = [
    { title: '類型', dataIndex: 'type', key: 'type', width: 80 },
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120 },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '結束日期', dataIndex: 'end_date', key: 'end_date', width: 100 },
    { title: '金額', dataIndex: 'amount', key: 'amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '手續費', dataIndex: 'fee', key: 'fee', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString() || 0}` : '-' },
    { title: '已收金額', dataIndex: 'received_amount', key: 'received_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString() || 0}` : '-' },
    { title: '繳費狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120 }
  ]

  const payableColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120 },
    { title: '類型', dataIndex: 'contract_type', key: 'contract_type', width: 80 },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '付款對象', dataIndex: 'payable_type', key: 'payable_type', width: 100 },
    { title: '公司代碼', dataIndex: 'company_code', key: 'company_code', width: 120 },
    { title: '金額', dataIndex: 'amount', key: 'amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '付款狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120 }
  ]

  const serviceColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120 },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150 },
    { title: '服務日期', dataIndex: 'service_date', key: 'service_date', width: 100 },
    { title: '確認日期', dataIndex: 'confirm_date', key: 'confirm_date', width: 100 },
    { title: '服務類型', dataIndex: 'service_type', key: 'service_type', width: 100 },
    { title: '維修公司代碼', dataIndex: 'repair_company_code', key: 'repair_company_code', width: 150 },
    { title: '總金額', dataIndex: 'total_amount', key: 'total_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '繳費狀況', dataIndex: 'payment_status', key: 'payment_status', width: 120 }
  ]

  const handleExport = async () => {
    setExporting(true)
    try {
      // 使用當前搜尋條件取得資料
      const [receivables, unpaid, paid, service] = await Promise.all([
        getReceivables(receivablesFilters).catch(() => []),
        getUnpaidPayables(payablesFilters).catch(() => []),
        getPaidPayables(payablesFilters).catch(() => []),
        getServiceExpenses(serviceFilters).catch(() => [])
      ])

      // 準備應收帳款資料
      const receivablesSheet = receivables.map(item => ({
        '類型': item.type || '',
        '合約編號': item.contract_code || '',
        '客戶代碼': item.customer_code || '',
        '客戶名稱': item.customer_name || '',
        '日期': item.date || '',
        '結束日期': item.end_date || '',
        '金額': item.amount || 0,
        '手續費': item.fee || 0,
        '已收金額': item.received_amount || 0,
        '應收總額': (item.amount || 0) + (item.fee || 0),
        '未收金額': ((item.amount || 0) + (item.fee || 0)) - (item.received_amount || 0),
        '繳費狀況': item.payment_status || ''
      }))

      // 總未收帳款（篩選未收款）
      const unpaidReceivablesSheet = receivablesSheet.filter(item => item.繳費狀況 !== '已收款')

      // 準備未出帳款資料
      const unpaidPayablesSheet = unpaid.map(item => ({
        '合約編號': item.contract_code || '',
        '類型': item.contract_type || '',
        '客戶代碼': item.customer_code || '',
        '客戶名稱': item.customer_name || '',
        '日期': item.date || '',
        '付款對象': item.payable_type || '',
        '公司代碼': item.company_code || '',
        '金額': item.amount || 0,
        '付款狀況': item.payment_status || ''
      }))

      // 準備已出帳款資料
      const paidPayablesSheet = paid.map(item => ({
        '合約編號': item.contract_code || '',
        '類型': item.contract_type || '',
        '客戶代碼': item.customer_code || '',
        '客戶名稱': item.customer_name || '',
        '日期': item.date || '',
        '付款對象': item.payable_type || '',
        '公司代碼': item.company_code || '',
        '金額': item.amount || 0,
        '付款狀況': item.payment_status || ''
      }))

      // 準備服務費用資料
      const serviceSheet = service.map(item => ({
        '合約編號': item.contract_code || '',
        '客戶代碼': item.customer_code || '',
        '客戶名稱': item.customer_name || '',
        '服務日期': item.service_date || '',
        '確認日期': item.confirm_date || '',
        '服務類型': item.service_type || '',
        '維修公司代碼': item.repair_company_code || '',
        '總金額': item.total_amount || 0,
        '繳費狀況': item.payment_status || ''
      }))

      // 建立 Excel 工作簿
      const wb = XLSX.utils.book_new()
      
      // 建立工作表
      if (receivablesSheet.length > 0) {
        const ws1 = XLSX.utils.json_to_sheet(receivablesSheet)
        XLSX.utils.book_append_sheet(wb, ws1, '總應收帳款')
      }
      
      if (unpaidReceivablesSheet.length > 0) {
        const ws2 = XLSX.utils.json_to_sheet(unpaidReceivablesSheet)
        XLSX.utils.book_append_sheet(wb, ws2, '總未收帳款')
      }
      
      if (unpaidPayablesSheet.length > 0) {
        const ws3 = XLSX.utils.json_to_sheet(unpaidPayablesSheet)
        XLSX.utils.book_append_sheet(wb, ws3, '未出帳款')
      }
      
      if (paidPayablesSheet.length > 0) {
        const ws4 = XLSX.utils.json_to_sheet(paidPayablesSheet)
        XLSX.utils.book_append_sheet(wb, ws4, '已出帳款')
      }
      
      if (serviceSheet.length > 0) {
        const ws5 = XLSX.utils.json_to_sheet(serviceSheet)
        XLSX.utils.book_append_sheet(wb, ws5, '服務費用')
      }

      // 檢查是否有資料
      const hasData = receivablesSheet.length > 0 || 
                     unpaidPayablesSheet.length > 0 || 
                     paidPayablesSheet.length > 0 || 
                     serviceSheet.length > 0
      
      if (!hasData) {
        setAlertType('warning')
        setAlertMessage('選定的日期範圍內沒有資料可匯出')
        setTimeout(() => setAlertMessage(null), 3000)
        setExporting(false)
        return
      }

      // 匯出檔案
      try {
        const fileName = `帳款資料_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`
        XLSX.writeFile(wb, fileName)
        
        setAlertType('success')
        setAlertMessage('匯出成功！')
        setTimeout(() => setAlertMessage(null), 3000)
      } catch (writeError) {
        console.error('XLSX.writeFile 錯誤', writeError)
        // 如果 writeFile 失敗，嘗試使用 Blob 方式
        try {
          const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
          const blob = new Blob([wbout], { type: 'application/octet-stream' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a')
          link.href = url
          link.download = `帳款資料_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          URL.revokeObjectURL(url)
          
          setAlertType('success')
          setAlertMessage('匯出成功！')
          setTimeout(() => setAlertMessage(null), 3000)
        } catch (blobError) {
          setAlertType('error')
          setAlertMessage('匯出失敗：' + (blobError.message || '無法建立檔案'))
          setTimeout(() => setAlertMessage(null), 5000)
          console.error('Blob 匯出錯誤', blobError)
        }
      }
    } catch (error) {
      const errorMsg = error?.message || error?.toString() || '未知錯誤'
      setAlertType('error')
      setAlertMessage('匯出失敗：' + errorMsg)
      setTimeout(() => setAlertMessage(null), 5000)
      console.error('匯出錯誤', error)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      {alertMessage && (
        <Alert
          message={alertMessage}
          type={alertType}
          closable
          onClose={() => setAlertMessage(null)}
          style={{ marginBottom: 16 }}
        />
      )}
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'flex-end' }}>
        <Button 
          type="primary" 
          icon={<DownloadOutlined />} 
          onClick={handleExport}
          loading={exporting}
        >
          匯出 Excel
        </Button>
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'receivables',
            label: '總應收帳款',
            children: (
              <>
                <ReceivablesSearchForm 
                  filters={receivablesFilters}
                  onSearch={setReceivablesFilters}
                />
                <Table
                  columns={receivablesColumns}
                  dataSource={receivablesData}
                  rowKey="id"
                  loading={loading}
                  scroll={{ x: 1200 }}
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              </>
            )
          },
          {
            key: 'unpaid-payable',
            label: '未出帳款',
            children: (
              <>
                <PayablesSearchForm 
                  filters={payablesFilters}
                  onSearch={setPayablesFilters}
                />
                <Table
                  columns={payableColumns}
                  dataSource={unpaidPayableData}
                  rowKey={(_, idx) => `unpaid-${idx}`}
                  loading={loading}
                  scroll={{ x: 1200 }}
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              </>
            )
          },
          {
            key: 'paid-payable',
            label: '已出帳款',
            children: (
              <>
                <PayablesSearchForm 
                  filters={payablesFilters}
                  onSearch={setPayablesFilters}
                />
                <Table
                  columns={payableColumns}
                  dataSource={paidPayableData}
                  rowKey={(_, idx) => `paid-${idx}`}
                  loading={loading}
                  scroll={{ x: 1200 }}
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              </>
            )
          },
          {
            key: 'service',
            label: '服務費用',
            children: (
              <>
                <ServiceSearchForm 
                  filters={serviceFilters}
                  onSearch={setServiceFilters}
                />
                <Table
                  columns={serviceColumns}
                  dataSource={serviceExpenseData}
                  rowKey="id"
                  loading={loading}
                  scroll={{ x: 1200 }}
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              </>
            )
          }
        ]}
      />
    </div>
  )
}

export default Accounts
