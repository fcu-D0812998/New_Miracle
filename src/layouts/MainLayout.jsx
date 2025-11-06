import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  UserOutlined,
  BankOutlined,
  FileTextOutlined,
  DollarOutlined,
  WalletOutlined,
} from '@ant-design/icons'

const { Header, Content, Sider } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '首頁' },
  { key: '/customers', icon: <UserOutlined />, label: '客戶資料' },
  { key: '/companies', icon: <BankOutlined />, label: '公司資料' },
  { key: '/contracts', icon: <FileTextOutlined />, label: '合約資料' },
  { key: '/accounts', icon: <DollarOutlined />, label: '帳款查詢' },
  { key: '/bank-ledger', icon: <WalletOutlined />, label: '銀行帳本' },
]

function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={200} style={{ background: '#001529' }}>
        <div style={{ 
          height: 64, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          color: '#fff',
          fontSize: 18,
          fontWeight: 'bold'
        }}>
          📊 記帳平台
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
          <h2 style={{ margin: 0, lineHeight: '64px' }}>印表機記帳管理系統</h2>
        </Header>
        <Content style={{ margin: '24px', background: '#fff', borderRadius: 4 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout



