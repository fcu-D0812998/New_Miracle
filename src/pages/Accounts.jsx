import { useState, useEffect } from 'react'
import { Tabs, Table, DatePicker, Space, Button } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getReceivables, getUnpaidPayables, getPaidPayables, getServiceExpenses } from '../services/api'

const { RangePicker } = DatePicker

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

  const handleExport = () => {
    message.info('匯出功能待實作')
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
