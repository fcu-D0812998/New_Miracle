import dayjs from 'dayjs'

const zhCollator = new Intl.Collator('zh-TW', {
  numeric: true,
  sensitivity: 'base'
})

const isEmpty = (value) => value === null || value === undefined || value === ''

const readValue = (record, accessor) => {
  if (typeof accessor === 'function') return accessor(record)
  return record?.[accessor]
}

const emptyCompare = (aValue, bValue, sortOrder) => {
  const aEmpty = isEmpty(aValue)
  const bEmpty = isEmpty(bValue)

  if (aEmpty && bEmpty) return 0
  if (!aEmpty && !bEmpty) return null

  const result = aEmpty ? 1 : -1
  return sortOrder === 'descend' ? -result : result
}

const toNumber = (value) => {
  if (isEmpty(value)) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const toTimestamp = (value) => {
  if (isEmpty(value)) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.valueOf() : null
}

export const textSorter = (accessor) => (a, b, sortOrder) => {
  const aValue = readValue(a, accessor)
  const bValue = readValue(b, accessor)
  const emptyResult = emptyCompare(aValue, bValue, sortOrder)
  if (emptyResult !== null) return emptyResult

  return zhCollator.compare(String(aValue), String(bValue))
}

export const numberSorter = (accessor) => (a, b, sortOrder) => {
  const aValue = toNumber(readValue(a, accessor))
  const bValue = toNumber(readValue(b, accessor))
  const emptyResult = emptyCompare(aValue, bValue, sortOrder)
  if (emptyResult !== null) return emptyResult

  return aValue - bValue
}

export const dateSorter = (accessor) => (a, b, sortOrder) => {
  const aValue = toTimestamp(readValue(a, accessor))
  const bValue = toTimestamp(readValue(b, accessor))
  const emptyResult = emptyCompare(aValue, bValue, sortOrder)
  if (emptyResult !== null) return emptyResult

  return aValue - bValue
}

export const booleanSorter = (accessor) => (a, b, sortOrder) => {
  const aValue = readValue(a, accessor)
  const bValue = readValue(b, accessor)
  const emptyResult = emptyCompare(aValue, bValue, sortOrder)
  if (emptyResult !== null) return emptyResult

  return Number(Boolean(aValue)) - Number(Boolean(bValue))
}

export const statusSorter = (accessor, orderMap = {}) => (a, b, sortOrder) => {
  const aValue = readValue(a, accessor)
  const bValue = readValue(b, accessor)
  const emptyResult = emptyCompare(aValue, bValue, sortOrder)
  if (emptyResult !== null) return emptyResult

  const aRank = orderMap[aValue]
  const bRank = orderMap[bValue]
  if (aRank !== undefined && bRank !== undefined) return aRank - bRank
  if (aRank !== undefined) return -1
  if (bRank !== undefined) return 1

  return zhCollator.compare(String(aValue), String(bValue))
}
