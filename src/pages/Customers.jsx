import { useState, useEffect } from 'react'
import { 
  Table, 
  Button, 
  Input, 
  Space, 
  Modal, 
  Form, 
  message,
  Popconfirm 
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons'
import { getCustomers, createCustomer, updateCustomer, deleteCustomer } from '../services/api'

const { TextArea } = Input

function Customers() {
  const [searchText, setSearchText] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [dataSource, setDataSource] = useState([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const loadData = async () => {
    setLoading(true)
    try {
      const data = await getCustomers(searchText || undefined)
      setDataSource(data)
    } catch (error) {
      message.error('載入資料失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [searchText])

  const columns = [
    { title: '客戶代碼', dataIndex: 'customer_code', key: 'customer_code', width: 120 },
    { title: '客戶名稱', dataIndex: 'name', key: 'name', width: 150 },
    { title: '聯絡人', dataIndex: 'contact_name', key: 'contact_name', width: 120 },
    { title: '手機', dataIndex: 'mobile', key: 'mobile', width: 120 },
    { title: '電話', dataIndex: 'phone', key: 'phone', width: 120 },
    { title: '地址', dataIndex: 'address', key: 'address', width: 200 },
    { title: 'Email', dataIndex: 'email', key: 'email', width: 150 },
    { title: '統編', dataIndex: 'tax_id', key: 'tax_id', width: 100 },
    { title: '負責業務', dataIndex: 'sales_rep_name', key: 'sales_rep_name', width: 120 },
    { title: '備註', dataIndex: 'remark', key: 'remark' },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          <Button 
            type="link" 
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            編輯
          </Button>
          <Popconfirm
            title="確定要刪除嗎？"
            onConfirm={() => handleDelete(record.customer_code)}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              刪除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const handleAdd = () => {
    setEditingRecord(null)
    form.resetFields()
    setIsModalOpen(true)
  }

  const handleEdit = (record) => {
    setEditingRecord(record)
    form.setFieldsValue(record)
    setIsModalOpen(true)
  }

  const handleDelete = async (customerCode) => {
    try {
      await deleteCustomer(customerCode)
      message.success('刪除成功')
      loadData()
    } catch (error) {
      message.error('刪除失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingRecord) {
        await updateCustomer(editingRecord.customer_code, values)
        message.success('更新成功')
      } else {
        await createCustomer(values)
        message.success('新增成功')
      }
      setIsModalOpen(false)
      form.resetFields()
      loadData()
    } catch (error) {
      if (error.errorFields) return
      message.error((editingRecord ? '更新' : '新增') + '失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Input
          placeholder="🔍 搜尋客戶（可搜尋任何欄位）"
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 400 }}
          allowClear
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增客戶
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={dataSource}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1500 }}
        pagination={{ pageSize: 10, showSizeChanger: true }}
      />

      <Modal
        title={editingRecord ? '編輯客戶' : '新增客戶'}
        open={isModalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalOpen(false)
          form.resetFields()
        }}
        width={800}
        okText="確定"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={editingRecord}
        >
          <Form.Item
            label="客戶代碼"
            name="customer_code"
            rules={[{ required: true, message: '請輸入客戶代碼' }]}
          >
            <Input disabled={!!editingRecord} />
          </Form.Item>
          
          <Form.Item
            label="客戶名稱"
            name="name"
            rules={[{ required: true, message: '請輸入客戶名稱' }]}
          >
            <Input />
          </Form.Item>

          <Space.Compact style={{ width: '100%' }}>
            <Form.Item label="聯絡人" name="contact_name" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="手機" name="mobile" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="電話" name="phone" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </Space.Compact>

          <Form.Item label="地址" name="address">
            <TextArea rows={2} />
          </Form.Item>

          <Space.Compact style={{ width: '100%' }}>
            <Form.Item label="Email" name="email" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="統編" name="tax_id" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item label="負責業務姓名" name="sales_rep_name" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </Space.Compact>

          <Form.Item label="備註" name="remark">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Customers
