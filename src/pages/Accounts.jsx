import { useState, useEffect } from 'react'
import { 
  Tabs, 
  Table, 
  DatePicker, 
  Space, 
  Button, 
  message 
} from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'
import { getReceivables, getUnpaidPayables, getPaidPayables, getServiceExpenses } from '../services/api'

const { RangePicker } = DatePicker

// 確保 message 在生產環境構建時不被移除（明確引用）
if (process.env.NODE_ENV === 'production') {
  // 強制引用 message，防止 tree-shaking
  void message
}

function Accounts() {
  const [dateRange, setDateRange] = useState([dayjs().subtract(1, 'month'), dayjs()])
  const [receivablesData, setReceivablesData] = useState([])
  const [unpaidPayableData, setUnpaidPayableData] = useState([])
  const [paidPayableData, setPaidPayableData] = useState([])
  const [serviceExpenseData, setServiceExpenseData] = useState([])
  const [loading, setLoading] = useState(false)

  const loadData = async () => {
    if (!dateRange || !dateRange[0] || !dateRange[1]) return
    
    setLoading(true)
    try {
      const fromDate = dateRange[0].format('YYYY-MM-DD')
      const toDate = dateRange[1].format('YYYY-MM-DD')
      
      const [receivables, unpaid, paid, service] = await Promise.all([
        getReceivables(fromDate, toDate).catch(() => []),
        getUnpaidPayables(fromDate, toDate).catch(() => []),
        getPaidPayables(fromDate, toDate).catch(() => []),
        getServiceExpenses(fromDate, toDate).catch(() => [])
      ])
      
      setReceivablesData(receivables)
      setUnpaidPayableData(unpaid)
      setPaidPayableData(paid)
      setServiceExpenseData(service)
    } catch (error) {
      console.error('載入資料失敗', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [dateRange])

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
    if (!dateRange || !dateRange[0] || !dateRange[1]) {
      message.warning('請先選擇日期範圍')
      return
    }

    try {
      const hideLoading = message.loading('正在匯出 Excel...', 0)
      
      const fromDate = dateRange[0].format('YYYY-MM-DD')
      const toDate = dateRange[1].format('YYYY-MM-DD')
      
      // 取得所有資料
      const [receivables, unpaid, paid, service] = await Promise.all([
        getReceivables(fromDate, toDate).catch(() => []),
        getUnpaidPayables(fromDate, toDate).catch(() => []),
        getPaidPayables(fromDate, toDate).catch(() => []),
        getServiceExpenses(fromDate, toDate).catch(() => [])
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
        hideLoading()
        message.warning('選定的日期範圍內沒有資料可匯出')
        return
      }

      // 匯出檔案
      try {
        const fileName = `帳款資料_${fromDate}_${toDate}.xlsx`
        XLSX.writeFile(wb, fileName)
        
        hideLoading()
        message.success('匯出成功！')
      } catch (writeError) {
        hideLoading()
        console.error('XLSX.writeFile 錯誤', writeError)
        // 如果 writeFile 失敗，嘗試使用 Blob 方式
        try {
          const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' })
          const blob = new Blob([wbout], { type: 'application/octet-stream' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a')
          link.href = url
          link.download = `帳款資料_${fromDate}_${toDate}.xlsx`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          URL.revokeObjectURL(url)
          
          message.success('匯出成功！')
        } catch (blobError) {
          message.error('匯出失敗：' + (blobError.message || '無法建立檔案'))
          console.error('Blob 匯出錯誤', blobError)
        }
      }
    } catch (error) {
      const errorMsg = error?.message || error?.toString() || '未知錯誤'
      message.error('匯出失敗：' + errorMsg)
      console.error('匯出錯誤', error)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <RangePicker
          value={dateRange}
          onChange={setDateRange}
          format="YYYY-MM-DD"
        />
        <Button type="primary" icon={<DownloadOutlined />} onClick={handleExport}>
          匯出 Excel
        </Button>
      </Space>

      <Tabs
        items={[
          {
            key: 'receivables',
            label: '總應收帳款',
            children: (
              <Table
                columns={receivablesColumns}
                dataSource={receivablesData}
                rowKey="id"
                loading={loading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10, showSizeChanger: true }}
              />
            )
          },
          {
            key: 'unpaid-payable',
            label: '未出帳款',
            children: (
              <Table
                columns={payableColumns}
                dataSource={unpaidPayableData}
                rowKey="id"
                loading={loading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10, showSizeChanger: true }}
              />
            )
          },
          {
            key: 'paid-payable',
            label: '已出帳款',
            children: (
              <Table
                columns={payableColumns}
                dataSource={paidPayableData}
                rowKey="id"
                loading={loading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10, showSizeChanger: true }}
              />
            )
          },
          {
            key: 'service',
            label: '服務費用',
            children: (
              <Table
                columns={serviceColumns}
                dataSource={serviceExpenseData}
                rowKey="id"
                loading={loading}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 10, showSizeChanger: true }}
              />
            )
          }
        ]}
      />
    </div>
  )
}

export default Accounts
