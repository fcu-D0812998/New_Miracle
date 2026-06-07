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
  Divider,
  AutoComplete,
  Upload,
  Alert
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined,
  UploadOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getBankLedger,
  getBankLedgerPayers,
  previewBankLedgerOcr,
  importBankLedgerOcrRows,
  createBankLedger,
  updateBankLedger,
  deleteBankLedger,
  getReconcilableReceivables,
  getReconcilableServiceExpenses,
  reconcileBankLedger,
  unreconcileBankLedger
} from '../services/api'
import { booleanSorter, dateSorter, numberSorter, textSorter } from '../utils/tableSorters'

const { TextArea } = Input
const { RangePicker } = DatePicker
const ACCOUNTING_PERIOD_OPTIONS = [
  { value: 'current', label: '本期' },
  { value: 'prior', label: '前帳' },
  { value: 'all', label: '全部' }
]

const formatMoney = (value) => `NT$ ${Number(value || 0).toLocaleString()}`
const normalizeSearchText = (value) => String(value || '').trim().toLowerCase()

const fileToBase64 = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.onerror = reject
  reader.readAsDataURL(file)
})

function BankLedger() {
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState(null)
  const [accountingPeriod, setAccountingPeriod] = useState('current')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isReconcileModalOpen, setIsReconcileModalOpen] = useState(false)
  const [isOcrModalOpen, setIsOcrModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [reconcilingRecord, setReconcilingRecord] = useState(null)
  const [dataSource, setDataSource] = useState([])
  const [loading, setLoading] = useState(false)
  const [reconcileLoading, setReconcileLoading] = useState(false)
  const [reconcilableReceivables, setReconcilableReceivables] = useState([])
  const [reconcilableServiceExpenses, setReconcilableServiceExpenses] = useState([])
  const [payerOptions, setPayerOptions] = useState([])
  const [ocrFiles, setOcrFiles] = useState([])
  const [ocrRows, setOcrRows] = useState([])
  const [ocrImages, setOcrImages] = useState([])
  const [ocrWarnings, setOcrWarnings] = useState([])
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrImporting, setOcrImporting] = useState(false)
  const [form] = Form.useForm()
  const [reconcileForm] = Form.useForm()
  const watchedLines = Form.useWatch('lines', reconcileForm) || []

  const loadData = async () => {
    setLoading(true)
    try {
      const fromDate = dateRange?.[0]?.format('YYYY-MM-DD')
      const toDate = dateRange?.[1]?.format('YYYY-MM-DD')
      const data = await getBankLedger(fromDate, toDate, searchText || undefined, accountingPeriod)
      setDataSource(data)
    } catch (error) {
      message.error('載入資料失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const loadPayerOptions = async () => {
    try {
      const payers = await getBankLedgerPayers()
      setPayerOptions(payers.map((payer) => ({ value: payer })))
    } catch (error) {
      message.error('載入對象選項失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  useEffect(() => {
    loadData()
  }, [dateRange, searchText, accountingPeriod])

  useEffect(() => {
    loadPayerOptions()
  }, [])

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

  const feeTotal = useMemo(
    () => watchedLines.reduce((sum, line) => sum + Number(line?.fee_amount || 0), 0),
    [watchedLines]
  )

  const isReconcilingExpense = (reconcilingRecord?.expense || 0) > 0
  const ledgerUsedTotal = allocatedTotal + (isReconcilingExpense ? feeTotal : 0)
  const remainingAmount = Math.max(ledgerAmount - ledgerUsedTotal, 0)

  const formatReceivablePeriod = (receivable) => {
    if (!receivable?.date) return '-'
    return receivable.end_date ? `${receivable.date} ~ ${receivable.end_date}` : receivable.date
  }

  const getReceivableOptionLabel = (item) => {
    const invoiceText = item.needs_invoice ? ` | 含稅 ${formatMoney(item.amount)} / 稅 ${formatMoney(item.tax_amount)}` : ''
    return `${item.contract_code} - ${item.customer_name} (${item.type}) | 收款期間：${formatReceivablePeriod(item)}${invoiceText}`
  }

  const getExpensePayeeName = (item) =>
    item?.payee_name || item?.vendor || '未指定付款對象'

  const getExpenseOptionLabel = (item) => {
    const itemType = item.expense_source === 'extra' ? (item.expense_category || '額外開銷') : item.service_type
    const description = item.expense_description ? ` | ${item.expense_description}` : ''
    return `付款對象：${getExpensePayeeName(item)} | ${itemType} | ${item.contract_code || '無合約'} - ${item.customer_name || '未綁定客戶'}${description}`
  }

  const getReconciledInfoText = (record) => {
    if (!record.is_reconciled) return ''
    if (record.reconciliation_lines?.length) {
      return record.reconciliation_lines
        .map((line) => [
          line.item_type,
          line.contract_code,
          line.customer_name,
          line.period,
          line.description,
          line.payee_name
        ].filter(Boolean).join(' / '))
        .join(' | ')
    }
    if (record.reconciled_ar_id) return `應收帳款 ${record.reconciled_ar_id} ${record.reconciled_ar_type || ''}`
    if (record.reconciled_service_expense_id) return `服務費用 ${record.reconciled_service_expense_id}`
    if (record.reconciled_payable_contract_code) {
      return `合約 ${record.reconciled_payable_contract_code} ${record.reconciled_payable_type || ''}`
    }
    return ''
  }

  const columns = [
    { title: '日期', dataIndex: 'txn_date', key: 'txn_date', width: 120, sorter: dateSorter('txn_date') },
    { title: '對象', dataIndex: 'payer', key: 'payer', width: 160, sorter: textSorter('payer') },
    { title: '支出金額', dataIndex: 'expense', key: 'expense', width: 120, sorter: numberSorter('expense'), render: (value) => value > 0 ? formatMoney(value) : '-' },
    { title: '收入金額', dataIndex: 'income', key: 'income', width: 120, sorter: numberSorter('income'), render: (value) => value > 0 ? formatMoney(value) : '-' },
    { title: '備註', dataIndex: 'note', key: 'note', width: 180, sorter: textSorter('note') },
    {
      title: '對帳狀態',
      dataIndex: 'is_reconciled',
      key: 'is_reconciled',
      width: 110,
      sorter: booleanSorter('is_reconciled'),
      render: (value) => value ? <Tag color="green">已對帳</Tag> : <Tag>未對帳</Tag>
    },
    {
      title: '對帳資訊',
      key: 'reconciled_info',
      width: 360,
      sorter: textSorter(getReconciledInfoText),
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
                    {line.payee_name ? `付款對象 ${line.payee_name} | ` : ''}
                    分攤 {formatMoney(line.allocated_amount)}
                    {line.fee_amount > 0 ? ` | 手續費 ${formatMoney(line.fee_amount)}` : ''}
                  </div>
                </div>
              ))}
              <div style={{ fontSize: 12, color: '#666' }}>
                已分攤 {formatMoney(record.reconciled_amount)}
                {record.reconciled_fee_total > 0 ? ` / 手續費 ${formatMoney(record.reconciled_fee_total)}` : ''}
                {' / '}剩餘 {formatMoney(record.unallocated_amount)}
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

  const openOcrModal = () => {
    setOcrFiles([])
    setOcrRows([])
    setOcrImages([])
    setOcrWarnings([])
    setIsOcrModalOpen(true)
  }

  const closeOcrModal = () => {
    setIsOcrModalOpen(false)
    setOcrFiles([])
    setOcrRows([])
    setOcrImages([])
    setOcrWarnings([])
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
      loadPayerOptions()
    } catch (error) {
      if (error.errorFields) return
      message.error((editingRecord ? '更新' : '新增') + '失敗：' + (error.response?.data?.detail || error.message))
    }
  }

  const handleOcrPreview = async () => {
    if (!ocrFiles.length) {
      message.warning('請先選擇帳本照片')
      return
    }

    setOcrLoading(true)
    try {
      const images = await Promise.all(ocrFiles.map(async (fileItem) => {
        const file = fileItem.originFileObj || fileItem
        return {
          filename: file.name || fileItem.name,
          mime_type: file.type || fileItem.type,
          content_base64: await fileToBase64(file)
        }
      }))
      const result = await previewBankLedgerOcr(images)
      setOcrImages(result.images || [])
      setOcrWarnings(result.warnings || [])
      setOcrRows((result.rows || []).map((row, index) => ({
        ...row,
        key: row.key || `ocr-${index}`
      })))
      message.success(`辨識完成，共產生 ${result.row_count || 0} 筆待確認資料`)
    } catch (error) {
      message.error('OCR 辨識失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setOcrLoading(false)
    }
  }

  const updateOcrRow = (key, field, value) => {
    setOcrRows((rows) => rows.map((row) => (
      row.key === key ? { ...row, [field]: value } : row
    )))
  }

  const deleteOcrRow = (key) => {
    setOcrRows((rows) => rows.filter((row) => row.key !== key))
  }

  const handleOcrImport = async () => {
    const rows = ocrRows.map((row) => ({
      txn_date: row.txn_date,
      payer: row.payer || null,
      expense: Number(row.expense || 0),
      income: Number(row.income || 0),
      note: row.note || null
    }))

    const invalidRow = rows.find((row) => (
      !row.txn_date
      || !dayjs(row.txn_date).isValid()
      || ((row.expense || 0) <= 0 && (row.income || 0) <= 0)
    ))
    if (invalidRow) {
      message.warning('請確認每筆資料都有日期，且至少有收入或支出金額')
      return
    }

    setOcrImporting(true)
    try {
      const result = await importBankLedgerOcrRows(rows)
      message.success(`匯入成功，共新增 ${result.inserted_count || rows.length} 筆銀行帳本資料`)
      closeOcrModal()
      await loadData()
      await loadPayerOptions()
    } catch (error) {
      message.error('匯入失敗：' + (error.response?.data?.detail || error.message))
    } finally {
      setOcrImporting(false)
    }
  }

  const handleExport = () => {
    message.info('匯出功能待實作')
  }

  const ocrColumns = [
    {
      title: '日期',
      dataIndex: 'txn_date',
      key: 'txn_date',
      width: 150,
      render: (value, record) => (
        <DatePicker
          value={value ? dayjs(value) : null}
          onChange={(_, dateString) => updateOcrRow(record.key, 'txn_date', dateString)}
          style={{ width: '100%' }}
        />
      )
    },
    {
      title: '對象／匯款人',
      dataIndex: 'payer',
      key: 'payer',
      width: 160,
      render: (value, record) => (
        <Input
          value={value}
          onChange={(event) => updateOcrRow(record.key, 'payer', event.target.value)}
        />
      )
    },
    {
      title: '支出',
      dataIndex: 'expense',
      key: 'expense',
      width: 130,
      render: (value, record) => (
        <InputNumber
          min={0}
          value={value}
          onChange={(nextValue) => updateOcrRow(record.key, 'expense', nextValue || 0)}
          style={{ width: '100%' }}
        />
      )
    },
    {
      title: '收入',
      dataIndex: 'income',
      key: 'income',
      width: 130,
      render: (value, record) => (
        <InputNumber
          min={0}
          value={value}
          onChange={(nextValue) => updateOcrRow(record.key, 'income', nextValue || 0)}
          style={{ width: '100%' }}
        />
      )
    },
    {
      title: '備註',
      dataIndex: 'note',
      key: 'note',
      width: 220,
      render: (value, record) => (
        <Input
          value={value}
          onChange={(event) => updateOcrRow(record.key, 'note', event.target.value)}
        />
      )
    },
    {
      title: 'OCR 原文',
      dataIndex: 'source_text',
      key: 'source_text',
      width: 260,
      render: (value) => (
        <div style={{ fontSize: 12, color: '#666', whiteSpace: 'normal' }}>
          {value || '-'}
        </div>
      )
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" danger onClick={() => deleteOcrRow(record.key)}>
          刪除
        </Button>
      )
    }
  ]

  const handleReconcile = async (record) => {
    setReconcilingRecord(record)
    setReconcileLoading(true)
    try {
      const targetAccountingPeriod = record.accounting_period || accountingPeriod || 'current'
      if (record.income > 0) {
        const receivables = await getReconcilableReceivables(undefined, undefined, targetAccountingPeriod)
        setReconcilableReceivables(receivables)
        setReconcilableServiceExpenses([])
        reconcileForm.setFieldsValue({ lines: [{ fee_amount: 0 }] })
      } else if (record.expense > 0) {
        const expenses = await getReconcilableServiceExpenses(undefined, undefined, targetAccountingPeriod)
        setReconcilableServiceExpenses(expenses)
        setReconcilableReceivables([])
        reconcileForm.setFieldsValue({ lines: [{ fee_amount: 0 }] })
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
          allocated_amount: line.allocated_amount,
          fee_amount: line.fee_amount || 0
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
          <Select
            value={accountingPeriod}
            onChange={setAccountingPeriod}
            options={ACCOUNTING_PERIOD_OPTIONS}
            style={{ width: 110 }}
          />
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
          <Button icon={<UploadOutlined />} onClick={openOcrModal}>照片匯入</Button>
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
            <AutoComplete
              options={payerOptions}
              filterOption={(inputValue, option) =>
                normalizeSearchText(option?.value).includes(normalizeSearchText(inputValue))
              }
              placeholder="輸入或搜尋對象／匯款人"
              allowClear
            />
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
            <p>
              <strong>已分攤：</strong>{formatMoney(allocatedTotal)}
              {feeTotal > 0 ? <> / <strong>手續費：</strong>{formatMoney(feeTotal)}</> : null}
              {' / '}<strong>剩餘：</strong>{formatMoney(remainingAmount)}
            </p>
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
                                        {item.needs_invoice ? ` | 含稅 ${formatMoney(item.amount)} / 稅 ${formatMoney(item.tax_amount)}` : ''}
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
                                        <strong>付款對象：{getExpensePayeeName(item)}</strong> <Tag color={item.expense_source === 'extra' ? 'purple' : 'blue'}>{item.expense_source === 'extra' ? (item.expense_category || '額外開銷') : item.service_type}</Tag>
                                      </div>
                                      <div style={{ fontSize: 12, color: '#666' }}>
                                        合約：{item.contract_code || '無合約'} - {item.customer_name || '未綁定客戶'} | 未付 {formatMoney(item.unpaid_amount)}
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
                      <Form.Item
                        {...field}
                        label="手續費"
                        name={[field.name, 'fee_amount']}
                        tooltip={reconcilingRecord?.expense > 0 ? '支出手續費只記錄在銀行對帳，不會加到服務費用已付金額' : undefined}
                        style={{ width: 160 }}
                      >
                        <InputNumber min={0} step={1} style={{ width: '100%' }} addonBefore="NT$" />
                      </Form.Item>
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
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ fee_amount: 0 })} block>
                  新增分攤
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      <Modal
        title="照片 OCR 匯入銀行帳本"
        open={isOcrModalOpen}
        onCancel={closeOcrModal}
        width={1180}
        destroyOnClose
        footer={[
          <Button key="cancel" onClick={closeOcrModal}>取消</Button>,
          <Button key="preview" icon={<UploadOutlined />} loading={ocrLoading} onClick={handleOcrPreview}>
            開始辨識
          </Button>,
          <Button
            key="import"
            type="primary"
            loading={ocrImporting}
            disabled={!ocrRows.length}
            onClick={handleOcrImport}
          >
            確認匯入
          </Button>
        ]}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="請先辨識照片，再逐筆確認日期、對象、收入、支出與備註。確認匯入前不會寫入銀行帳本。"
          />
          <Upload
            accept="image/*"
            multiple
            maxCount={5}
            fileList={ocrFiles}
            beforeUpload={() => false}
            onChange={({ fileList }) => setOcrFiles(fileList)}
            onRemove={(file) => {
              setOcrFiles((files) => files.filter((item) => item.uid !== file.uid))
              return true
            }}
          >
            <Button icon={<UploadOutlined />}>選擇帳本照片</Button>
          </Upload>
          {ocrWarnings.map((warning) => (
            <Alert key={warning} type="warning" showIcon message={warning} />
          ))}
          {!!ocrImages.length && (
            <div style={{ fontSize: 13, color: '#666' }}>
              {ocrImages.map((image) => `${image.filename}：${image.row_count} 筆`).join(' / ')}
            </div>
          )}
          <Table
            columns={ocrColumns}
            dataSource={ocrRows}
            rowKey="key"
            pagination={{ pageSize: 8 }}
            scroll={{ x: 1130 }}
            locale={{ emptyText: '尚未產生待匯入資料' }}
          />
        </Space>
      </Modal>
    </div>
  )
}

export default BankLedger
