import { Card, Row, Col, Statistic } from 'antd'
import { UserOutlined, BankOutlined, FileTextOutlined, DollarOutlined } from '@ant-design/icons'

function Dashboard() {
  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 24 }}>📊 首頁</h1>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="客戶總數"
              value={0}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="公司總數"
              value={0}
              prefix={<BankOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="合約總數"
              value={0}
              prefix={<FileTextOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="未收帳款"
              value={0}
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



