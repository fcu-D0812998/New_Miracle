import { useState, useEffect } from 'react'
import { Button, Card, Col, message, Row, Space, Spin, Statistic, Table, Tag } from 'antd'
import { UserOutlined, BankOutlined, FileTextOutlined } from '@ant-design/icons'
import { 
  getCustomers, 
  getCompanies, 
  getLeasingContracts, 
  getBuyoutContracts, 
  getReceivables,
  getExpiringLeasingContracts,
  renewLeasingContract
} from '../services/api'
import { dateSorter, numberSorter, statusSorter, textSorter } from '../utils/tableSorters'

const CONTRACT_STATUS_ORDER = { active: 0, paused: 1 }
const currentYear = new Date().getFullYear()

const formatMoney = (value) => value ? `NT$ ${Number(value).toLocaleString()}` : '-'

const renderStatusTag = (status) => {
  if (status === 'paused') {
    return <Tag color="volcano">暫停</Tag>
  }
  return <Tag color="green">使用中</Tag>
}

function Dashboard() {
  const [stats, setStats] = useState({
    customers: 0,
    companies: 0,
    contracts: 0,
    unpaidReceivables: 0
  })
  const [loading, setLoading] = useState(true)
  const [expiringContracts, setExpiringContracts] = useState([])
  const [renewingCode, setRenewingCode] = useState(null)

  const loadDashboard = async () => {
    setLoading(true)
    try {
      const [customers, companies, leasing, buyout, receivables, expiring] = await Promise.all([
        getCustomers(),
        getCompanies(),
        getLeasingContracts(),
        getBuyoutContracts(),
        getReceivables(),
        getExpiringLeasingContracts(currentYear)
      ])

      const unpaidTotal = receivables
        .filter(r => r.payment_status !== '已收款')
        .reduce((sum, r) => {
          const total = (r.amount || 0) + (r.fee || 0)
          const received = r.received_amount || 0
          return sum + (total - received)
        }, 0)

      setStats({
        customers: customers.length,
        companies: companies.length,
        contracts: leasing.length + buyout.length,
        unpaidReceivables: unpaidTotal
      })
      setExpiringContracts(expiring)
    } catch (error) {
      console.error('載入首頁資料失敗:', error)
      message.error('載入首頁資料失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  const handleRenew = async (contractCode) => {
    setRenewingCode(contractCode)
    try {
      const newContract = await renewLeasingContract(contractCode)
      message.success(`續約成功，新合約編號：${newContract.contract_code}`)
      await loadDashboard()
    } catch (error) {
      message.error('續約失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setRenewingCode(null)
    }
  }

  const expiringColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code') },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 180, sorter: textSorter('customer_name') },
    { title: '起始日', dataIndex: 'start_date', key: 'start_date', width: 110, sorter: dateSorter('start_date') },
    { title: '結束日', dataIndex: 'end_date', key: 'end_date', width: 110, sorter: dateSorter('end_date') },
    { title: '機型', dataIndex: 'model', key: 'model', width: 150, sorter: textSorter('model'), render: (value) => value || '-' },
    { title: '台數', dataIndex: 'quantity', key: 'quantity', width: 80, sorter: numberSorter('quantity') },
    { title: '月租金', dataIndex: 'monthly_rent', key: 'monthly_rent', width: 120, sorter: numberSorter('monthly_rent'), render: formatMoney },
    { title: '合約期數', dataIndex: 'contract_months', key: 'contract_months', width: 100, sorter: numberSorter('contract_months') },
    { title: '狀態', dataIndex: 'status', key: 'status', width: 90, sorter: statusSorter('status', CONTRACT_STATUS_ORDER), render: renderStatusTag },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right',
      render: (_, record) => (
        <Button
          type="link"
          disabled={record.status !== 'active'}
          loading={renewingCode === record.contract_code}
          onClick={() => handleRenew(record.contract_code)}
        >
          續約
        </Button>
      )
    }
  ]

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 24 }}>首頁</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="客戶總數"
              value={stats.customers}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="公司總數"
              value={stats.companies}
              prefix={<BankOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="合約總數"
              value={stats.contracts}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="未收帳款"
              value={stats.unpaidReceivables}
              prefix="NT$"
              precision={2}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={`${currentYear} 年到期合約`}
        style={{ marginTop: 24 }}
        extra={<Tag color="blue">{expiringContracts.length} 筆</Tag>}
      >
        <Table
          columns={expiringColumns}
          dataSource={expiringContracts}
          rowKey="contract_code"
          pagination={{ pageSize: 8 }}
          scroll={{ x: 1260 }}
          locale={{ emptyText: `${currentYear} 年沒有到期租賃合約` }}
        />
        <Space style={{ marginTop: 12 }}>
          <Tag color="green">使用中可續約</Tag>
          <Tag color="volcano">暫停不可續約</Tag>
        </Space>
      </Card>
    </div>
  )
}

export default Dashboard



