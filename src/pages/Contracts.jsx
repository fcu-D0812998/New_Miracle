import { useState, useEffect } from 'react'
import { Tabs, Table, Button, Input, Space, Modal, Form, InputNumber, DatePicker, Select, message, Popconfirm, Tag, Switch } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { 
  getLeasingContracts, getBuyoutContracts,
  createLeasingContract, createBuyoutContract,
  updateLeasingContract, updateBuyoutContract,
  deleteLeasingContract, deleteBuyoutContract,
  pauseLeasingContract, resumeLeasingContract,
  pauseBuyoutContract, resumeBuyoutContract,
  getCustomers, getCompanies
} from '../services/api'

function Contracts() {
  const [searchText, setSearchText] = useState('')
  const [activeTab, setActiveTab] = useState('leasing')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [leasingData, setLeasingData] = useState([])
  const [buyoutData, setBuyoutData] = useState([])
  const [customers, setCustomers] = useState([])
  const [salesCompanies, setSalesCompanies] = useState([])
  const [serviceCompanies, setServiceCompanies] = useState([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const loadOptions = async () => {
    try {
      const [customersData, salesData, serviceData] = await Promise.all([
        getCustomers(),
        getCompanies('sales'),
        getCompanies('service')
      ])
      setCustomers(customersData.map(c => ({ value: c.customer_code, label: c.name })))
      setSalesCompanies(salesData.map(c => ({ value: c.company_code, label: c.name })))
      setServiceCompanies(serviceData.map(c => ({ value: c.company_code, label: c.name })))
    } catch (error) {
      message.error('載入選項資料失敗')
    }
  }

  const loadLeasingData = async () => {
    setLoading(true)
    try {
      const data = await getLeasingContracts(searchText || undefined)
      setLeasingData(data)
    } catch (error) {
      message.error('載入租賃合約失敗')
    } finally {
      setLoading(false)
    }
  }

  const loadBuyoutData = async () => {
    setLoading(true)
    try {
      const data = await getBuyoutContracts(searchText || undefined)
      setBuyoutData(data)
    } catch (error) {
      message.error('載入買斷合約失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOptions()
  }, [])

  useEffect(() => {
    if (activeTab === 'leasing') {
      loadLeasingData()
    } else {
      loadBuyoutData()
    }
  }, [activeTab, searchText])

  useEffect(() => {
    if (isModalOpen) {
      if (editingRecord?.contract_code) {
        // 編輯模式：設定表單值
        if (editingRecord.type === 'leasing') {
          const formValues = {
            ...editingRecord,
            start_date: editingRecord.start_date ? dayjs(editingRecord.start_date) : null,
            needs_invoice: editingRecord.needs_invoice ?? false
          }
          form.setFieldsValue(formValues)
        } else if (editingRecord.type === 'buyout') {
          const formValues = {
            ...editingRecord,
            deal_date: editingRecord.deal_date ? dayjs(editingRecord.deal_date) : null,
            needs_invoice: editingRecord.needs_invoice ?? false
          }
          form.setFieldsValue(formValues)
        }
      } else {
        // 新增模式：重置表單
        form.resetFields()
      }
    }
  }, [isModalOpen, editingRecord])

  const renderStatusTag = (status) => {
    if (status === 'paused') {
      return <Tag color="volcano">暫停</Tag>
    }
    return <Tag color="green">使用中</Tag>
  }

  const leasingColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120 },
    { title: '狀態', dataIndex: 'status', key: 'status', width: 90, render: renderStatusTag },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150 },
    { title: '起始日', dataIndex: 'start_date', key: 'start_date', width: 100 },
    { title: '機型', dataIndex: 'model', key: 'model', width: 150 },
    { title: '台數', dataIndex: 'quantity', key: 'quantity', width: 80 },
    { title: '月租金', dataIndex: 'monthly_rent', key: 'monthly_rent', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '繳費週期(月)', dataIndex: 'payment_cycle_months', key: 'payment_cycle_months', width: 120 },
    { title: '超印', dataIndex: 'overprint', key: 'overprint', width: 150 },
    { title: '合約期數(月)', dataIndex: 'contract_months', key: 'contract_months', width: 120 },
    { title: '需開發票', dataIndex: 'needs_invoice', key: 'needs_invoice', width: 100, render: (val) => val ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '業務金額', dataIndex: 'sales_amount', key: 'sales_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '維護金額', dataIndex: 'service_amount', key: 'service_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    {
      title: '操作',
      key: 'action',
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record, 'leasing')}>編輯</Button>
          {record.status === 'active' ? (
            <Popconfirm title="確定要暫停這份合約？" onConfirm={() => handlePause(record.contract_code, 'leasing')}>
              <Button type="link" danger>暫停</Button>
            </Popconfirm>
          ) : (
            <Popconfirm title="確定要恢復這份合約？" onConfirm={() => handleResume(record.contract_code, 'leasing')}>
              <Button type="link">恢復</Button>
            </Popconfirm>
          )}
          <Popconfirm title="確定要刪除嗎？" onConfirm={() => handleDelete(record.contract_code, 'leasing')}>
            <Button type="link" danger icon={<DeleteOutlined />}>刪除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const buyoutColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120 },
    { title: '狀態', dataIndex: 'status', key: 'status', width: 90, render: renderStatusTag },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150 },
    { title: '成交日期', dataIndex: 'deal_date', key: 'deal_date', width: 100 },
    { title: '成交金額', dataIndex: 'deal_amount', key: 'deal_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '需開發票', dataIndex: 'needs_invoice', key: 'needs_invoice', width: 100, render: (val) => val ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '業務金額', dataIndex: 'sales_amount', key: 'sales_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '維護金額', dataIndex: 'service_amount', key: 'service_amount', width: 120, render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    {
      title: '操作',
      key: 'action',
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record, 'buyout')}>編輯</Button>
          {record.status === 'active' ? (
            <Popconfirm title="確定要暫停這份合約？" onConfirm={() => handlePause(record.contract_code, 'buyout')}>
              <Button type="link" danger>暫停</Button>
            </Popconfirm>
          ) : (
            <Popconfirm title="確定要恢復這份合約？" onConfirm={() => handleResume(record.contract_code, 'buyout')}>
              <Button type="link">恢復</Button>
            </Popconfirm>
          )}
          <Popconfirm title="確定要刪除嗎？" onConfirm={() => handleDelete(record.contract_code, 'buyout')}>
            <Button type="link" danger icon={<DeleteOutlined />}>刪除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const handleAdd = (type) => {
    setEditingRecord({ type })
    form.resetFields()
    setIsModalOpen(true)
  }

  const handleEdit = (record, type) => {
    setEditingRecord({ ...record, type })
    form.resetFields()
    const formValues = type === 'leasing' 
      ? { ...record, start_date: dayjs(record.start_date), needs_invoice: record.needs_invoice ?? false }
      : { ...record, deal_date: dayjs(record.deal_date), needs_invoice: record.needs_invoice ?? false }
    form.setFieldsValue(formValues)
    setIsModalOpen(true)
  }

  const handleCancel = () => {
    setIsModalOpen(false)
    setEditingRecord(null)
    form.resetFields()
  }

  const handleDelete = async (contractCode, type) => {
    try {
      if (type === 'leasing') {
        await deleteLeasingContract(contractCode)
        loadLeasingData()
      } else {
        await deleteBuyoutContract(contractCode)
        loadBuyoutData()
      }
      message.success('刪除成功')
    } catch (error) {
      message.error('刪除失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handlePause = async (contractCode, type) => {
    setLoading(true)
    try {
      if (type === 'leasing') {
        await pauseLeasingContract(contractCode)
        message.success('合約已暫停，應收帳款已取消')
        await loadLeasingData()
      } else {
        await pauseBuyoutContract(contractCode)
        message.success('合約已暫停，應收帳款已取消')
        await loadBuyoutData()
      }
    } catch (error) {
      message.error('暫停失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleResume = async (contractCode, type) => {
    setLoading(true)
    const payload = { resume_date: dayjs().format('YYYY-MM-DD') }
    try {
      if (type === 'leasing') {
        await resumeLeasingContract(contractCode, payload)
        message.success('合約已恢復，未來應收帳款已重新生成')
        await loadLeasingData()
      } else {
        await resumeBuyoutContract(contractCode, payload)
        message.success('合約已恢復，未來應收帳款已重新生成')
        await loadBuyoutData()
      }
    } catch (error) {
      message.error('恢復失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const submitData = {
        ...values,
        start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
        deal_date: values.deal_date ? values.deal_date.format('YYYY-MM-DD') : null,
        customer_code: values.customer_name  // customer_name 實際是 customer_code
      }
      delete submitData.customer_name

      if (editingRecord.contract_code) {
        if (editingRecord.type === 'leasing') {
          await updateLeasingContract(editingRecord.contract_code, submitData)
          message.success('更新成功！已重新生成應收帳款。')
          loadLeasingData()
        } else {
          await updateBuyoutContract(editingRecord.contract_code, submitData)
          message.success('更新成功！已重新生成應收帳款。')
          loadBuyoutData()
        }
      } else {
        if (editingRecord.type === 'leasing') {
          await createLeasingContract(submitData)
          message.success('新增成功！已自動生成應收帳款。')
          loadLeasingData()
        } else {
          await createBuyoutContract(submitData)
          message.success('新增成功！已自動生成應收帳款。')
          loadBuyoutData()
        }
      }
      setIsModalOpen(false)
      setEditingRecord(null)
      form.resetFields()
    } catch (error) {
      if (error.errorFields) return
      message.error((editingRecord?.contract_code ? '更新' : '新增') + '失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const renderLeasingForm = () => (
    <>
      <Form.Item label="合約編號" name="contract_code" rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name" rules={[{ required: true }]}>
        <Select options={customers} />
      </Form.Item>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="合約起始日" name="start_date" rules={[{ required: true }]} style={{ flex: 1 }}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="機型" name="model" style={{ flex: 1 }}>
          <Input />
        </Form.Item>
        <Form.Item label="台數" name="quantity" style={{ flex: 1 }}>
          <InputNumber min={1} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="月租金" name="monthly_rent" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="繳費週期(月)" name="payment_cycle_months" style={{ flex: 1 }}>
          <InputNumber min={1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="合約期數(月)" name="contract_months" style={{ flex: 1 }}>
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
      <Form.Item 
        label="是否需要開發票" 
        name="needs_invoice" 
        valuePropName="checked"
        tooltip="勾選後，月租金將自動 × 1.05（含稅），金額會直接存入資料庫"
      >
        <Switch checkedChildren="要開" unCheckedChildren="不開" />
      </Form.Item>
      <Form.Item label="超印描述" name="overprint">
        <Input />
      </Form.Item>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="業務公司" name="sales_company_code" style={{ flex: 1 }}>
          <Select options={salesCompanies} placeholder="不指定" allowClear />
        </Form.Item>
        <Form.Item label="業務金額" name="sales_amount" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="維護公司" name="service_company_code" style={{ flex: 1 }}>
          <Select options={serviceCompanies} placeholder="不指定" allowClear />
        </Form.Item>
        <Form.Item label="維護金額" name="service_amount" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
    </>
  )

  const renderBuyoutForm = () => (
    <>
      <Form.Item label="合約編號" name="contract_code" rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item label="客戶名稱" name="customer_name" rules={[{ required: true }]}>
        <Select options={customers} />
      </Form.Item>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="成交日期" name="deal_date" rules={[{ required: true }]} style={{ flex: 1 }}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="成交金額" name="deal_amount" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
      <Form.Item 
        label="是否需要開發票" 
        name="needs_invoice" 
        valuePropName="checked"
        tooltip="勾選後，成交金額將自動 × 1.05（含稅），金額會直接存入資料庫"
      >
        <Switch checkedChildren="要開" unCheckedChildren="不開" />
      </Form.Item>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="業務公司" name="sales_company_code" style={{ flex: 1 }}>
          <Select options={salesCompanies} placeholder="不指定" allowClear />
        </Form.Item>
        <Form.Item label="業務金額" name="sales_amount" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="維護公司" name="service_company_code" style={{ flex: 1 }}>
          <Select options={serviceCompanies} placeholder="不指定" allowClear />
        </Form.Item>
        <Form.Item label="維護金額" name="service_amount" style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
    </>
  )

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Input
          placeholder="🔍 搜尋合約（可搜尋任何欄位）"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 400 }}
          allowClear
        />
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'leasing',
            label: '租賃合約',
            children: (
              <>
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => handleAdd('leasing')}>
                    新增租賃合約
                  </Button>
                </Space>
                <Table
                  columns={leasingColumns}
                  dataSource={leasingData}
                  rowKey="id"
                  loading={loading}
                  scroll={{ x: 1500 }}
                  pagination={{ pageSize: 10, showSizeChanger: true }}
                />
              </>
            )
          },
          {
            key: 'buyout',
            label: '買斷合約',
            children: (
              <>
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => handleAdd('buyout')}>
                    新增買斷合約
                  </Button>
                </Space>
                <Table
                  columns={buyoutColumns}
                  dataSource={buyoutData}
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

      <Modal
        title={editingRecord?.contract_code ? (editingRecord.type === 'leasing' ? '編輯租賃合約' : '編輯買斷合約') : (editingRecord?.type === 'leasing' ? '新增租賃合約' : '新增買斷合約')}
        open={isModalOpen}
        onOk={handleSubmit}
        onCancel={handleCancel}
        width={900}
        okText="確定"
        cancelText="取消"
        destroyOnClose
      >
        <Form 
          key={editingRecord?.contract_code ? `${editingRecord.type}-${editingRecord.contract_code}` : `new-${editingRecord?.type || 'leasing'}`}
          form={form} 
          layout="vertical"
        >
          {editingRecord?.type === 'leasing' ? renderLeasingForm() : renderBuyoutForm()}
        </Form>
      </Modal>
    </div>
  )
}

export default Contracts
