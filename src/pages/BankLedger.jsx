import { useEffect, useMemo, useState } from 'react'
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
  Tag,
  Divider
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined
} from '@ant-design/icons'
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

const formatMoney = (value) => `NT$ ${Number(value || 0).toLocaleString()}`

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
  const watchedLines = Form.useWatch('lines', reconcileForm) || []

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
    if (!isModalOpen) return
    if (editingRecord) {
      form.setFieldsValue({
        ...editingRecord,
        txn_date: dayjs(editingRecord.txn_date),
        transaction_type: editingRecord.income > 0 ? 'income' : 'expense',
        amount: editingRecord.income > 0 ? editingRecord.income : editingRecord.expense
      })
    } else {
      form.resetFields()
    }
  }, [isModalOpen, editingRecord, form])

  const ledgerAmount = useMemo(() => {
    if (!reconcilingRecord) return 0
    return reconcilingRecord.income > 0 ? reconcilingRecord.income : reconcilingRecord.expense
  }, [reconcilingRecord])

  const allocatedTotal = useMemo(
    () => watchedLines.reduce((sum, line) => sum + Number(line?.allocated_amount || 0), 0),
    [watchedLines]
  )

  const remainingAmount = Math.max(ledgerAmount - allocatedTotal, 0)

  const formatReceivablePeriod = (receivable) => {
    if (!receivable?.date) return '-'
    return receivable.end_date ? `${receivable.date} ~ ${receivable.end_date}` : receivable.date
  }

  const getReceivableOptionLabel = (item) =>
    `${item.contract_code} - ${item.customer_name} (${item.type}) | 收款期間：${formatReceivablePeriod(item)}`

  const getExpenseOptionLabel = (item) => {
    const itemType = item.expense_source === 'extra' ? (item.expense_category || '額外開銷') : item.service_type
    const description = item.expense_description ? ` | ${item.expense_description}` : ''
    return `${item.contract_code || '無合約'} - ${item.customer_name || '未綁定客戶'} (${itemType})${description}`
  }

  const columns = [
    { title: '日期', dataIndex: 'txn_date', key: 'txn_date', width: 120 },
    { title: '對象', dataIndex: 'payer', key: 'payer', width: 160 },
    { title: '支出金額', dataIndex: 'expense', key: 'expense', width: 120, render: (value) => value > 0 ? formatMoney(value) : '-' },
    { title: '收入金額', dataIndex: 'income', key: 'income', width: 120, render: (value) => value > 0 ? formatMoney(value) : '-' },
    { title: '備註', dataIndex: 'note', key: 'note', width: 180 },
    {
      title: '對帳狀態',
      dataIndex: 'is_reconciled',
      key: 'is_reconciled',
      width: 110,
      render: (value) => value ? <Tag color="green">已對帳</Tag> : <Tag>未對帳</Tag>
    },
    {
      title: '對帳資訊',
      key: 'reconciled_info',
      width: 360,
      render: (_, record) => {
        if (!record.is_reconciled) return '-'

        if (record.reconciliation_lines?.length) {
          return (
            <div>
              {record.reconciliation_lines.map((line) => (
                <div key={line.id} style={{ marginBottom: 6 }}>
                  <strong>{line.item_type}</strong>
                  {line.contract_code ? ` / ${line.contract_code}` : ''}
                  {line.customer_name ? ` / ${line.customer_name}` : ''}
                  {line.period ? ` / ${line.period}` : ''}
                  {line.description ? ` / ${line.description}` : ''}
                  <div style={{ fontSize: 12, color: '#666' }}>
                    分攤 {formatMoney(line.allocated_amount)}
                    {line.fee_amount > 0 ? ` | 手續費 ${formatMoney(line.fee_amount)}` : ''}
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 12, color: '#666' }}>
                已分攤 {formatMoney(record.reconciled_amount)} / 剩餘 {formatMoney(record.unallocated_amount)}
              </div>
            </div>
          )
        }

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
      width: 220,
      fixed: 'right',
      render: (_, record) => (
        <Space>
          {!record.is_reconciled && (
            <Button type="link" icon={<CheckCircleOutlined />} onClick={() => handleReconcile(record)}>
              對帳
            </Button>
          )}
          {record.is_reconciled && (
            <Button type="link" icon={<CloseCircleOutlined />} onClick={() => handleUnreconcile(record)}>
              取消對帳
            </Button>
          )}
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            編輯
          </Button>
          <Popconfirm title="確定要刪除這筆資料嗎？" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" danger icon={<DeleteOutlined />}>刪除</Button>
          </Popconfirm>
        </Space>
      )
    }
  ]

  const handleAdd = () => {
    setEditingRecord(null)
    form.resetFields()
    setIsModalOpen(true)
  }

  const handleEdit = (record) => {
    setEditingRecord(record)
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
      if (record.income > 0) {
        const receivables = await getReconcilableReceivables()
        setReconcilableReceivables(receivables)
        setReconcilableServiceExpenses([])
        reconcileForm.setFieldsValue({ lines: [{ fee_amount: 0 }] })
      } else if (record.expense > 0) {
        const expenses = await getReconcilableServiceExpenses()
        setReconcilableServiceExpenses(expenses)
        setReconcilableReceivables([])
        reconcileForm.setFieldsValue({ lines: [{}] })
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
      const isIncome = reconcilingRecord.income > 0
      const lines = (values.lines || []).map((line) => {
        if (isIncome) {
          const selected = reconcilableReceivables.find((item) => item.id === line.target_id)
          return {
            target_id: line.target_id,
            allocated_amount: line.allocated_amount,
            fee_amount: line.fee_amount || 0,
            ar_type: selected?.type === '租賃' ? 'leasing' : 'buyout'
          }
        }
        return {
          target_id: line.target_id,
          allocated_amount: line.allocated_amount
        }
      })

      await reconcileBankLedger(reconcilingRecord.id, {
        reconcile_type: isIncome ? 'receivable' : 'service_expense',
        auto_update: true,
        lines
      })

      message.success('對帳成功')
      setIsReconcileModalOpen(false)
      setReconcilingRecord(null)
      setReconcilableReceivables([])
      setReconcilableServiceExpenses([])
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
          <RangePicker value={dateRange} onChange={setDateRange} format="YYYY-MM-DD" />
          <Input
            placeholder="搜尋關鍵字"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            style={{ width: 300 }}
            allowClear
          />
        </Space>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增資料</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExport}>匯出 Excel</Button>
        </Space>
      </Space>

      <Space style={{ marginBottom: 16, padding: 12, background: '#f0f0f0', borderRadius: 4 }}>
        <span><strong>總收入：</strong>{formatMoney(totalIncome)}</span>
        <span><strong>總支出：</strong>{formatMoney(totalExpense)}</span>
        <span><strong>淨額：</strong>{formatMoney(netAmount)}</span>
      </Space>

      <Table columns={columns} dataSource={dataSource} rowKey="id" loading={loading} scroll={{ x: 1500 }} />

      <Modal
        title={editingRecord ? '編輯銀行帳本' : '新增銀行帳本'}
        open={isModalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setIsModalOpen(false)
          setEditingRecord(null)
          form.resetFields()
        }}
        width={600}
        okText="儲存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item label="日期" name="txn_date" rules={[{ required: true, message: '請選擇日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="對象" name="payer">
            <Input />
          </Form.Item>
          <Form.Item label="交易類型" name="transaction_type" rules={[{ required: true, message: '請選擇交易類型' }]}>
            <Radio.Group>
              <Radio value="income">收入</Radio>
              <Radio value="expense">支出</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, curr) => prev.transaction_type !== curr.transaction_type}>
            {({ getFieldValue }) => (
              <Form.Item label={getFieldValue('transaction_type') === 'income' ? '收入金額' : '支出金額'} name="amount" rules={[{ required: true, message: '請輸入金額' }]}>
                <InputNumber min={0} step={100} style={{ width: '100%' }} />
              </Form.Item>
            )}
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
        width={960}
        okText="儲存對帳"
        cancelText="取消"
        destroyOnClose
        confirmLoading={reconcileLoading}
      >
        {reconcilingRecord && (
          <div style={{ marginBottom: 16, padding: 12, background: '#f0f0f0', borderRadius: 4 }}>
            <p><strong>日期：</strong>{reconcilingRecord.txn_date}</p>
            <p><strong>對象：</strong>{reconcilingRecord.payer || '-'}</p>
            <p><strong>流水金額：</strong>{formatMoney(ledgerAmount)}</p>
            <p><strong>已分攤：</strong>{formatMoney(allocatedTotal)} / <strong>剩餘：</strong>{formatMoney(remainingAmount)}</p>
            <p><strong>備註：</strong>{reconcilingRecord.note || '-'}</p>
          </div>
        )}

        <Form form={reconcileForm} layout="vertical" initialValues={{ lines: [{}] }}>
          <Form.List name="lines">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, index) => (
                  <div key={field.key} style={{ marginBottom: 12, padding: 12, border: '1px solid #f0f0f0', borderRadius: 8 }}>
                    <Space align="start" style={{ display: 'flex' }}>
                      <Form.Item
                        {...field}
                        label={reconcilingRecord?.income > 0 ? '應收帳款' : '支出項目'}
                        name={[field.name, 'target_id']}
                        rules={[{ required: true, message: '請選擇項目' }]}
                        style={{ width: 420 }}
                      >
                        <Select
                          placeholder={reconcilingRecord?.income > 0 ? '選擇應收帳款' : '選擇支出項目'}
                          showSearch
                          filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
                          options={
                            reconcilingRecord?.income > 0
                              ? reconcilableReceivables.map((item) => ({
                                  value: item.id,
                                  label: getReceivableOptionLabel(item),
                                  children: (
                                    <div>
                                      <div>
                                        <strong>{item.contract_code}</strong> - {item.customer_name} <Tag color={item.type === '租賃' ? 'blue' : 'green'}>{item.type}</Tag>
                                      </div>
                                      <div style={{ fontSize: 12, color: '#666' }}>
                                        收款期間：{formatReceivablePeriod(item)} | 未收 {formatMoney(item.unpaid_amount)}
                                      </div>
                                    </div>
                                  )
                                }))
                              : reconcilableServiceExpenses.map((item) => ({
                                  value: item.id,
                                  label: getExpenseOptionLabel(item),
                                  children: (
                                    <div>
                                      <div>
                                        <strong>{item.contract_code || '無合約'}</strong> - {item.customer_name || '未綁定客戶'} <Tag color={item.expense_source === 'extra' ? 'purple' : 'blue'}>{item.expense_source === 'extra' ? (item.expense_category || '額外開銷') : item.service_type}</Tag>
                                      </div>
                                      <div style={{ fontSize: 12, color: '#666' }}>
                                        未付 {formatMoney(item.unpaid_amount)}
                                        {item.expense_description ? ` | ${item.expense_description}` : ''}
                                      </div>
                                    </div>
                                  )
                                }))
                          }
                          optionRender={(option) => option.data.children}
                        />
                      </Form.Item>
                      <Form.Item
                        {...field}
                        label="分攤金額"
                        name={[field.name, 'allocated_amount']}
                        rules={[{ required: true, message: '請輸入金額' }]}
                        style={{ width: 180 }}
                      >
                        <InputNumber min={0.01} step={100} style={{ width: '100%' }} addonBefore="NT$" />
                      </Form.Item>
                      {reconcilingRecord?.income > 0 && (
                        <Form.Item
                          {...field}
                          label="手續費"
                          name={[field.name, 'fee_amount']}
                          style={{ width: 160 }}
                        >
                          <InputNumber min={0} step={1} style={{ width: '100%' }} addonBefore="NT$" />
                        </Form.Item>
                      )}
                      <Button
                        danger
                        type="text"
                        icon={<MinusCircleOutlined />}
                        onClick={() => remove(field.name)}
                        disabled={fields.length === 1}
                        style={{ marginTop: 30 }}
                      />
                    </Space>
                    {index < fields.length - 1 && <Divider style={{ margin: '12px 0 0' }} />}
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add(reconcilingRecord?.income > 0 ? { fee_amount: 0 } : {})} block>
                  新增分攤
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  )
}

export default BankLedger
