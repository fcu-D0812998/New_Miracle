"""帳款金額與開發票稅額計算。"""

RECEIVABLE_UNPAID = "未收"
RECEIVABLE_PARTIAL = "部分收款"
RECEIVABLE_PAID = "已收款"

INVOICE_TAX_RATE = 0.05
INVOICE_TAX_MULTIPLIER = 1 + INVOICE_TAX_RATE


def to_float(value) -> float:
    return float(value) if value is not None else 0.0


def apply_invoice_tax(amount, needs_invoice: bool) -> float:
    base_amount = to_float(amount)
    if not needs_invoice:
        return base_amount
    return base_amount * INVOICE_TAX_MULTIPLIER


def remove_invoice_tax(amount, needs_invoice: bool) -> float:
    base_amount = to_float(amount)
    if not needs_invoice:
        return base_amount
    return base_amount / INVOICE_TAX_MULTIPLIER


def invoice_tax_amount(amount, needs_invoice: bool) -> float:
    if not needs_invoice:
        return 0.0
    return to_float(amount) * INVOICE_TAX_RATE


def calculate_receivable_status(untaxed_amount, fee, received_amount, needs_invoice: bool = False) -> str:
    invoice_amount = apply_invoice_tax(untaxed_amount, needs_invoice)
    total_due = max(invoice_amount, 0.0) + max(to_float(fee), 0.0)
    received = max(to_float(received_amount), 0.0)
    if received >= total_due and total_due > 0:
        return RECEIVABLE_PAID
    if received > 0:
        return RECEIVABLE_PARTIAL
    return RECEIVABLE_UNPAID
