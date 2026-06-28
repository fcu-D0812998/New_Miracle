import { useState, useEffect } from 'react'
import { Tabs, Table, Button, Input, Space, Modal, Form, InputNumber, DatePicker, Select, message, Popconfirm, Tag, Switch, AutoComplete } from 'antd'
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
import { booleanSorter, dateSorter, numberSorter, statusSorter, textSorter } from '../utils/tableSorters'

const ACCOUNTING_PERIOD_OPTIONS = [
  { value: 'current', label: '本期' },
  { value: 'prior', label: '前帳' },
  { value: 'all', label: '全部' }
]
const CONTRACT_STATUS_ORDER = { active: 0, paused: 1 }
const normalizeSearchText = (value) => String(value || '').trim().toLowerCase()

function Contracts() {
  const [searchText, setSearchText] = useState('')
  const [accountingPeriod, setAccountingPeriod] = useState('current')
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
  const [salesAmountTouched, setSalesAmountTouched] = useState(false)

  const loadOptions = async () => {
    try {
      const [customersData, salesData, serviceData] = await Promise.all([
        getCustomers(),
        getCompanies('sales'),
        getCompanies('service')
      ])
      setCustomers(customersData.map(c => ({
        value: c.name || c.customer_code,
        label: `${c.name || c.customer_code}（${c.customer_code}）`,
        searchText: `${c.name || ''} ${c.customer_code || ''}`,
        customer_code: c.customer_code,
        name: c.name
      })))
      setSalesCompanies(salesData.map(c => ({ value: c.company_code, label: c.name })))
      setServiceCompanies(serviceData.map(c => ({ value: c.company_code, label: c.name })))
    } catch (error) {
      message.error('載入選項資料失敗')
    }
  }

  const loadLeasingData = async () => {
    setLoading(true)
    try {
      const data = await getLeasingContracts(searchText || undefined, accountingPeriod)
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
      const data = await getBuyoutContracts(searchText || undefined, accountingPeriod)
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
  }, [activeTab, searchText, accountingPeriod])

  useEffect(() => {
    if (isModalOpen) {
      if (editingRecord?.contract_code) {
        // 編輯模式：設定表單值
        if (editingRecord.type === 'leasing') {
          const formValues = {
            ...editingRecord,
            customer_code: editingRecord.customer_name || editingRecord.customer_code,
            start_date: editingRecord.start_date ? dayjs(editingRecord.start_date) : null,
            needs_invoice: editingRecord.needs_invoice ?? false
          }
          form.setFieldsValue(formValues)
        } else if (editingRecord.type === 'buyout') {
          const formValues = {
            ...editingRecord,
            customer_code: editingRecord.customer_name || editingRecord.customer_code,
            deal_date: editingRecord.deal_date ? dayjs(editingRecord.deal_date) : null,
            needs_invoice: editingRecord.needs_invoice ?? false
          }
          form.setFieldsValue(formValues)
        }
      } else {
        // 新增模式：重置表單
        form.resetFields()
        form.setFieldsValue({
          quantity: 1,
          payment_cycle_months: 1,
          needs_invoice: false
        })
      }
    }
  }, [isModalOpen, editingRecord])

  const renderStatusTag = (status) => {
    if (status === 'paused') {
      return <Tag color="volcano">暫停</Tag>
    }
    return <Tag color="green">使用中</Tag>
  }

  const getDefaultLeasingSalesAmount = (monthlyRent) => {
    const rent = Number(monthlyRent || 0)
    return rent > 0 ? rent * 2 : null
  }

  const isDefaultLeasingSalesAmount = (salesAmount, monthlyRent) => {
    if (salesAmount === null || salesAmount === undefined) return false
    const defaultAmount = getDefaultLeasingSalesAmount(monthlyRent)
    if (defaultAmount === null) return false
    return Math.abs(Number(salesAmount) - defaultAmount) < 0.000001
  }

  const handleMonthlyRentChange = (value) => {
    if (editingRecord?.type !== 'leasing' || salesAmountTouched) return
    form.setFieldValue('sales_amount', getDefaultLeasingSalesAmount(value))
  }

  const resolveCustomerInput = (value) => {
    const normalized = normalizeSearchText(value)
    const matchedCustomer = customers.find((customer) =>
      normalizeSearchText(customer.name) === normalized
      || normalizeSearchText(customer.customer_code) === normalized
    )
    return matchedCustomer?.customer_code || value
  }

  const customerFilterOption = (inputValue, option) =>
    normalizeSearchText(option?.searchText || option?.label || option?.value).includes(normalizeSearchText(inputValue))

  const leasingColumns = [
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code') },
    { title: '狀態', dataIndex: 'status', key: 'status', width: 90, sorter: statusSorter('status', CONTRACT_STATUS_ORDER), render: renderStatusTag },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120, sorter: textSorter('customer_code') },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150, sorter: textSorter('customer_name') },
    { title: '起始日', dataIndex: 'start_date', key: 'start_date', width: 100, sorter: dateSorter('start_date') },
    { title: '機型', dataIndex: 'model', key: 'model', width: 150, sorter: textSorter('model') },
    { title: '台數', dataIndex: 'quantity', key: 'quantity', width: 80, sorter: numberSorter('quantity') },
    { title: '月租金', dataIndex: 'monthly_rent', key: 'monthly_rent', width: 120, sorter: numberSorter('monthly_rent'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '繳費週期(月)', dataIndex: 'payment_cycle_months', key: 'payment_cycle_months', width: 120, sorter: numberSorter('payment_cycle_months') },
    { title: '超印', dataIndex: 'overprint', key: 'overprint', width: 150, sorter: textSorter('overprint') },
    { title: '合約期數(月)', dataIndex: 'contract_months', key: 'contract_months', width: 120, sorter: numberSorter('contract_months') },
    { title: '需開發票', dataIndex: 'needs_invoice', key: 'needs_invoice', width: 100, sorter: booleanSorter('needs_invoice'), render: (val) => val ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '業務金額', dataIndex: 'sales_amount', key: 'sales_amount', width: 120, sorter: numberSorter('sales_amount'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '維護金額', dataIndex: 'service_amount', key: 'service_amount', width: 120, sorter: numberSorter('service_amount'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
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
    { title: '合約編號', dataIndex: 'contract_code', key: 'contract_code', width: 120, sorter: textSorter('contract_code') },
    { title: '狀態', dataIndex: 'status', key: 'status', width: 90, sorter: statusSorter('status', CONTRACT_STATUS_ORDER), render: renderStatusTag },
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120, sorter: textSorter('customer_code') },
    { title: '客戶名稱', dataIndex: 'customer_name', key: 'customer_name', width: 150, sorter: textSorter('customer_name') },
    { title: '成交日期', dataIndex: 'deal_date', key: 'deal_date', width: 100, sorter: dateSorter('deal_date') },
    { title: '成交金額', dataIndex: 'deal_amount', key: 'deal_amount', width: 120, sorter: numberSorter('deal_amount'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '需開發票', dataIndex: 'needs_invoice', key: 'needs_invoice', width: 100, sorter: booleanSorter('needs_invoice'), render: (val) => val ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '業務金額', dataIndex: 'sales_amount', key: 'sales_amount', width: 120, sorter: numberSorter('sales_amount'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
    { title: '維護金額', dataIndex: 'service_amount', key: 'service_amount', width: 120, sorter: numberSorter('service_amount'), render: (val) => val ? `NT$ ${val?.toLocaleString()}` : '-' },
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
    setSalesAmountTouched(false)
    form.resetFields()
    form.setFieldsValue({
      quantity: 1,
      payment_cycle_months: 1,
      needs_invoice: false
    })
    setIsModalOpen(true)
  }

  const handleEdit = (record, type) => {
    setEditingRecord({ ...record, type })
    setSalesAmountTouched(
      type !== 'leasing'
        || (
          record.sales_amount !== null
          && record.sales_amount !== undefined
          && !isDefaultLeasingSalesAmount(record.sales_amount, record.monthly_rent)
        )
    )
    form.resetFields()
    const formValues = type === 'leasing' 
      ? { ...record, customer_code: record.customer_name || record.customer_code, start_date: dayjs(record.start_date), needs_invoice: record.needs_invoice ?? false }
      : { ...record, customer_code: record.customer_name || record.customer_code, deal_date: dayjs(record.deal_date), needs_invoice: record.needs_invoice ?? false }
    form.setFieldsValue(formValues)
    setIsModalOpen(true)
  }

  const handleCancel = () => {
    setIsModalOpen(false)
    setEditingRecord(null)
    setSalesAmountTouched(false)
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
        customer_code: resolveCustomerInput(values.customer_code),
        start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
        deal_date: values.deal_date ? values.deal_date.format('YYYY-MM-DD') : null
      }

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
      setSalesAmountTouched(false)
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
      <Form.Item label="客戶名稱" name="customer_code" rules={[{ required: true }]}>
        <AutoComplete
          options={customers}
          filterOption={customerFilterOption}
          placeholder="輸入或搜尋客戶名稱"
          allowClear
        />
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
        <Form.Item label="月租金" name="monthly_rent" rules={[{ required: true, message: '請輸入月租金' }]} style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} onChange={handleMonthlyRentChange} />
        </Form.Item>
        <Form.Item label="繳費週期(月)" name="payment_cycle_months" rules={[{ required: true, message: '請輸入繳費週期' }]} style={{ flex: 1 }}>
          <InputNumber min={1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="合約期數(月)" name="contract_months" rules={[{ required: true, message: '請輸入合約期數' }]} style={{ flex: 1 }}>
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
      <Form.Item 
        label="是否需要開發票" 
        name="needs_invoice" 
        valuePropName="checked"
        tooltip="勾選後，月租金仍以未稅保存；帳款查詢與對帳會另計 5% 稅金"
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
          <InputNumber min={0} step={100} style={{ width: '100%' }} onChange={() => setSalesAmountTouched(true)} />
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
      <Form.Item label="客戶名稱" name="customer_code" rules={[{ required: true }]}>
        <AutoComplete
          options={customers}
          filterOption={customerFilterOption}
          placeholder="輸入或搜尋客戶名稱"
          allowClear
        />
      </Form.Item>
      <Space.Compact style={{ width: '100%' }}>
        <Form.Item label="成交日期" name="deal_date" rules={[{ required: true }]} style={{ flex: 1 }}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="成交金額" name="deal_amount" rules={[{ required: true, message: '請輸入成交金額' }]} style={{ flex: 1 }}>
          <InputNumber min={0} step={100} style={{ width: '100%' }} />
        </Form.Item>
      </Space.Compact>
      <Form.Item 
        label="是否需要開發票" 
        name="needs_invoice" 
        valuePropName="checked"
        tooltip="勾選後，成交金額仍以未稅保存；帳款查詢與對帳會另計 5% 稅金"
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
        <Space>
          <Select
            value={accountingPeriod}
            onChange={setAccountingPeriod}
            options={ACCOUNTING_PERIOD_OPTIONS}
            style={{ width: 110 }}
          />
          <Input
            placeholder="搜尋合約（可搜尋任何欄位）"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 400 }}
            allowClear
          />
        </Space>
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
