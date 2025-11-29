import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Spin } from 'antd'
import { UserOutlined, BankOutlined, FileTextOutlined, DollarOutlined } from '@ant-design/icons'
import { 
  getCustomers, 
  getCompanies, 
  getLeasingContracts, 
  getBuyoutContracts, 
  getReceivables 
} from '../services/api'

function Dashboard() {
  const [stats, setStats] = useState({
    customers: 0,
    companies: 0,
    contracts: 0,
    unpaidReceivables: 0
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      try {
        const [customers, companies, leasing, buyout, receivables] = await Promise.all([
          getCustomers(),
          getCompanies(),
          getLeasingContracts(),
          getBuyoutContracts(),
          getReceivables()
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
      } catch (error) {
        console.error('載入統計資料失敗:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [])

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 24 }}>📊 首頁</h1>
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
    </div>
  )
}

export default Dashboard



