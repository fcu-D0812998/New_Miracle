import { useState, useEffect } from 'react'
import { 
  Table, 
  Button, 
  Space, 
  Modal, 
  Form, 
  DatePicker,
  InputNumber,
  Input,
  Radio,
  message,
  Popconfirm 
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, DownloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getBankLedger, createBankLedger, updateBankLedger, deleteBankLedger } from '../services/api'

const { TextArea } = Input
const { RangePicker } = DatePicker

function BankLedger() {
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [dataSource, setDataSource] = useState([])
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const loadData = async () => {
    setLoading(true)
    try {
      const fromDate = dateRange?.[0]?.format('YYYY-MM-DD')
      const toDate = dateRange?.[1]?.format('YYYY-MM-DD')
      const data = await getBankLedger(fromDate, toDate, searchText || undefined)
      setDataSource(data)
    } catch (error) {
      message.error('載入資料失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [dateRange, searchText])

  const columns = [
    { title: '日期', dataIndex: 'txn_date', key: 'txn_date', width: 120 },
    { title: '匯款人', dataIndex: 'payer', key: 'payer', width: 150 },
    { 
      title: '支出金額', 
      dataIndex: 'expense', 
      key: 'expense', 
      width: 120,
      render: (val) => val > 0 ? `NT$ ${val?.toLocaleString()}` : '-'
    },
    { 
      title: '收入金額', 
      dataIndex: 'income', 
      key: 'income', 
      width: 120,
      render: (val) => val > 0 ? `NT$ ${val?.toLocaleString()}` : '-'
    },
    { title: '備註', dataIndex: 'note', key: 'note', width: 200 },
    { 
      title: '已對帳', 
      dataIndex: 'is_reconciled', 
      key: 'is_reconciled', 
      width: 100,
      render: (val) => val ? '✓' : '-'
    },
    { 
      title: '對應帳款', 
      key: 'reconciled_info',
      width: 200,
      render: (_, record) => {
        if (!record.is_reconciled) return '-'
        if (record.reconciled_ar_id) {
          return `應收帳款 #${record.reconciled_ar_id} (${record.reconciled_ar_type})`
        }
        if (record.reconciled_payable_contract_code) {
          return `合約 ${record.reconciled_payable_contract_code} (${record.reconciled_payable_type})`
        }
        return '-'
      }
    },
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
            onConfirm={() => handleDelete(record.id)}
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
    const formValues = {
      ...record,
      txn_date: dayjs(record.txn_date),
      transaction_type: record.income > 0 ? 'income' : 'expense',
      amount: record.income > 0 ? record.income : record.expense
    }
    form.setFieldsValue(formValues)
    setIsModalOpen(true)
  }

  const handleDelete = async (id) => {
    try {
      await deleteBankLedger(id)
      message.success('刪除成功')
      loadData()
    } catch (error) {
      message.error('刪除失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const submitData = {
        txn_date: values.txn_date.format('YYYY-MM-DD'),
        payer: values.payer,
        expense: values.transaction_type === 'expense' ? values.amount : 0,
        income: values.transaction_type === 'income' ? values.amount : 0,
        note: values.note
      }

      if (editingRecord) {
        await updateBankLedger(editingRecord.id, submitData)
        message.success('更新成功')
      } else {
        await createBankLedger(submitData)
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

  const handleExport = () => {
    message.info('匯出功能待實作')
  }

  const totalExpense = dataSource.reduce((sum, item) => sum + (item.expense || 0), 0)
  const totalIncome = dataSource.reduce((sum, item) => sum + (item.income || 0), 0)
  const netAmount = totalIncome - totalExpense

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <RangePicker
            value={dateRange}
            onChange={setDateRange}
            format="YYYY-MM-DD"
          />
          <Input
            placeholder="🔍 搜尋"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 300 }}
            allowClear
          />
        </Space>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增記錄
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>
            匯出 Excel
          </Button>
        </Space>
      </Space>

      <Space style={{ marginBottom: 16, padding: '12px', background: '#f0f0f0', borderRadius: 4 }}>
        <span><strong>總收入：</strong>NT$ {totalIncome.toLocaleString()}</span>
        <span><strong>總支出：</strong>NT$ {totalExpense.toLocaleString()}</span>
        <span><strong>淨額：</strong>NT$ {netAmount.toLocaleString()}</span>
      </Space>

      <Table
        columns={columns}
        dataSource={dataSource}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1200 }}
        pagination={{ pageSize: 10, showSizeChanger: true }}
      />

      <Modal
        title={editingRecord ? '編輯帳本記錄' : '新增帳本記錄'}
        open={isModalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalOpen(false)
          form.resetFields()
        }}
        width={600}
        okText="確定"
        cancelText="取消"
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={editingRecord}
        >
          <Form.Item
            label="日期"
            name="txn_date"
            rules={[{ required: true, message: '請選擇日期' }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            label="匯款人"
            name="payer"
          >
            <Input />
          </Form.Item>

          <Form.Item
            label="交易類型"
            name="transaction_type"
            rules={[{ required: true, message: '請選擇交易類型' }]}
          >
            <Radio.Group>
              <Radio value="income">收入</Radio>
              <Radio value="expense">支出</Radio>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) => prevValues.transaction_type !== currentValues.transaction_type}
          >
            {({ getFieldValue }) => {
              const transactionType = getFieldValue('transaction_type')
              return (
                <Form.Item
                  label={transactionType === 'income' ? '收入金額' : '支出金額'}
                  name="amount"
                  rules={[{ required: true, message: '請輸入金額' }]}
                >
                  <InputNumber min={0} step={100} style={{ width: '100%' }} />
                </Form.Item>
              )
            }}
          </Form.Item>

          <Form.Item label="備註" name="note">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default BankLedger
