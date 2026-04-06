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
  Popconfirm,
  Select,
  Tag
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, DownloadOutlined, SearchOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { 
  getBankLedger, 
  createBankLedger, 
  updateBankLedger, 
  deleteBankLedger,
  getReconcilableReceivables,
  getReconcilableServiceExpenses,
  reconcileBankLedger,
  unreconcileBankLedger
} from '../services/api'

const { TextArea } = Input
const { RangePicker } = DatePicker

function BankLedger() {
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isReconcileModalOpen, setIsReconcileModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [reconcilingRecord, setReconcilingRecord] = useState(null)
  const [dataSource, setDataSource] = useState([])
  const [loading, setLoading] = useState(false)
  const [reconcileLoading, setReconcileLoading] = useState(false)
  const [reconcilableReceivables, setReconcilableReceivables] = useState([])
  const [reconcilableServiceExpenses, setReconcilableServiceExpenses] = useState([])
  const [form] = Form.useForm()
  const [reconcileForm] = Form.useForm()

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

  useEffect(() => {
    if (isModalOpen) {
      if (editingRecord) {
        const formValues = {
          ...editingRecord,
          txn_date: dayjs(editingRecord.txn_date),
          transaction_type: editingRecord.income > 0 ? 'income' : 'expense',
          amount: editingRecord.income > 0 ? editingRecord.income : editingRecord.expense
        }
        form.setFieldsValue(formValues)
      } else {
        form.resetFields()
      }
    }
  }, [isModalOpen, editingRecord])

  const formatReceivablePeriod = (receivable) => {
    if (!receivable?.date) return '-'
    return receivable.end_date ? `${receivable.date} ~ ${receivable.end_date}` : receivable.date
  }

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
        if (record.reconciled_service_expense_id) {
          return `服務費用 #${record.reconciled_service_expense_id}`
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
      width: 200,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          {!record.is_reconciled && (
            <Button 
              type="link" 
              icon={<CheckCircleOutlined />}
              onClick={() => handleReconcile(record)}
            >
              對帳
            </Button>
          )}
          {record.is_reconciled && (
            <Button 
              type="link" 
              icon={<CloseCircleOutlined />}
              onClick={() => handleUnreconcile(record)}
            >
              取消對帳
            </Button>
          )}
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
    form.resetFields()
    const formValues = {
      ...record,
      txn_date: dayjs(record.txn_date),
      transaction_type: record.income > 0 ? 'income' : 'expense',
      amount: record.income > 0 ? record.income : record.expense
    }
    form.setFieldsValue(formValues)
    setIsModalOpen(true)
  }

  const handleCancel = () => {
    setIsModalOpen(false)
    setEditingRecord(null)
    form.resetFields()
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
      setEditingRecord(null)
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

  const handleReconcile = async (record) => {
    setReconcilingRecord(record)
    setReconcileLoading(true)
    try {
      // 根據記錄類型載入可對帳的資料
      if (record.income > 0) {
        // 收入對帳：載入應收帳款
        const receivables = await getReconcilableReceivables()
        setReconcilableReceivables(receivables)
        setReconcilableServiceExpenses([])
      } else if (record.expense > 0) {
        // 支出對帳：載入服務費用
        const expenses = await getReconcilableServiceExpenses()
        setReconcilableServiceExpenses(expenses)
        setReconcilableReceivables([])
      }
      reconcileForm.resetFields()
      if (record.income > 0) {
        reconcileForm.setFieldsValue({ fee_amount: 0 })
      }
      setIsReconcileModalOpen(true)
    } catch (error) {
      message.error('載入可對帳資料失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setReconcileLoading(false)
    }
  }

  const handleUnreconcile = async (record) => {
    try {
      await unreconcileBankLedger(record.id, true)
      message.success('取消對帳成功')
      loadData()
    } catch (error) {
      message.error('取消對帳失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleReconcileSubmit = async () => {
    try {
      const values = await reconcileForm.validateFields()
      const reconcileData = {
        reconcile_type: reconcilingRecord.income > 0 ? 'receivable' : 'service_expense',
        auto_update: true
      }

      if (reconcilingRecord.income > 0) {
        // 收入對帳
        const selectedReceivable = reconcilableReceivables.find(r => r.id === values.receivable_id)
        if (!selectedReceivable) {
          message.error('請選擇應收帳款')
          return
        }
        reconcileData.ar_id = values.receivable_id
        reconcileData.ar_type = selectedReceivable.type === '租賃' ? 'leasing' : 'buyout'
        reconcileData.fee_amount = values.fee_amount || 0
      } else {
        // 支出對帳
        reconcileData.service_expense_id = values.service_expense_id
      }

      await reconcileBankLedger(reconcilingRecord.id, reconcileData)
      message.success('對帳成功')
      setIsReconcileModalOpen(false)
      setReconcilingRecord(null)
      reconcileForm.resetFields()
      loadData()
    } catch (error) {
      if (error.errorFields) return
      message.error('對帳失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleReconcileCancel = () => {
    setIsReconcileModalOpen(false)
    setReconcilingRecord(null)
    setReconcilableReceivables([])
    setReconcilableServiceExpenses([])
    reconcileForm.resetFields()
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
        onCancel={handleCancel}
        width={600}
        okText="確定"
        cancelText="取消"
        destroyOnClose
      >
        <Form
          key={editingRecord ? editingRecord.id : 'new'}
          form={form}
          layout="vertical"
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

      <Modal
        title="對帳"
        open={isReconcileModalOpen}
        onOk={handleReconcileSubmit}
        onCancel={handleReconcileCancel}
        width={800}
        okText="確定對帳"
        cancelText="取消"
        destroyOnClose
        confirmLoading={reconcileLoading}
      >
        {reconcilingRecord && (
          <div style={{ marginBottom: 16, padding: 12, background: '#f0f0f0', borderRadius: 4 }}>
            <p><strong>日期：</strong>{reconcilingRecord.txn_date}</p>
            <p><strong>匯款人：</strong>{reconcilingRecord.payer || '-'}</p>
            <p><strong>金額：</strong>
              {reconcilingRecord.income > 0 
                ? `收入 NT$ ${reconcilingRecord.income.toLocaleString()}`
                : `支出 NT$ ${reconcilingRecord.expense.toLocaleString()}`
              }
            </p>
            <p><strong>備註：</strong>{reconcilingRecord.note || '-'}</p>
          </div>
        )}

          <Form
            form={reconcileForm}
            layout="vertical"
          >
            {reconcilingRecord?.income > 0 && (
              <>
                <Form.Item
                  label="選擇應收帳款"
                  name="receivable_id"
                  rules={[{ required: true, message: '請選擇應收帳款' }]}
                >
                  <Select
                    placeholder="請選擇應收帳款"
                    showSearch
                    filterOption={(input, option) =>
                      (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                    }
                    loading={reconcileLoading}
                  >
                    {reconcilableReceivables.map(ar => (
                      <Select.Option 
                        key={ar.id} 
                        value={ar.id}
                        label={`${ar.contract_code} - ${ar.customer_name} (${ar.type}) | 收款期間：${formatReceivablePeriod(ar)}`}
                      >
                        <div>
                          <div><strong>{ar.contract_code}</strong> - {ar.customer_name} <Tag color={ar.type === '租賃' ? 'blue' : 'green'}>{ar.type}</Tag></div>
                          <div style={{ fontSize: '12px', color: '#666' }}>
                            收款期間：{formatReceivablePeriod(ar)} |
                          </div>
                          <div style={{ fontSize: '12px', color: '#666' }}>
                            應收：NT$ {ar.amount.toLocaleString()} + 手續費：NT$ {ar.fee.toLocaleString()} = NT$ {(ar.amount + ar.fee).toLocaleString()} | 
                            已收：NT$ {ar.received_amount.toLocaleString()} | 
                            未收：NT$ {ar.unpaid_amount.toLocaleString()} | 
                            狀態：<Tag color={ar.payment_status === '未收' ? 'red' : ar.payment_status === '部分收款' ? 'orange' : 'green'}>{ar.payment_status}</Tag>
                          </div>
                        </div>
                      </Select.Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item
                  label="手續費"
                  name="fee_amount"
                  tooltip="若本次對帳有額外手續費，會累加到這筆應收帳款，取消對帳時也會一併還原"
                >
                  <InputNumber
                    min={0}
                    step={1}
                    style={{ width: '100%' }}
                    addonBefore="NT$"
                    placeholder="沒有可填 0"
                  />
                </Form.Item>
              </>
            )}

          {reconcilingRecord?.expense > 0 && (
            <Form.Item
              label="選擇服務費用"
              name="service_expense_id"
              rules={[{ required: true, message: '請選擇服務費用' }]}
            >
              <Select
                placeholder="請選擇服務費用"
                showSearch
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
                loading={reconcileLoading}
              >
                {reconcilableServiceExpenses.map(se => (
                  <Select.Option 
                    key={se.id} 
                    value={se.id}
                    label={`${se.contract_code} - ${se.customer_name} (${se.service_type})`}
                  >
                    <div>
                      <div><strong>{se.contract_code}</strong> - {se.customer_name} <Tag color={se.service_type === '業務' ? 'blue' : 'purple'}>{se.service_type}</Tag></div>
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        金額：NT$ {se.total_amount.toLocaleString()} | 
                        狀態：<Tag color={se.payment_status === '未收' ? 'red' : se.payment_status === '部分收款' ? 'orange' : 'green'}>{se.payment_status}</Tag>
                      </div>
                    </div>
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}

export default BankLedger
