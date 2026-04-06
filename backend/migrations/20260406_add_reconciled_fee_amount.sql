ALTER TABLE bank_ledger
ADD COLUMN IF NOT EXISTS reconciled_fee_amount NUMERIC DEFAULT 0;
