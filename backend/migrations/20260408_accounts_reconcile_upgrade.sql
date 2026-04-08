ALTER TABLE ar_leasing
ADD COLUMN IF NOT EXISTS adjusted_amount NUMERIC;

ALTER TABLE ar_buyout
ADD COLUMN IF NOT EXISTS adjusted_amount NUMERIC;

ALTER TABLE service_expense
ADD COLUMN IF NOT EXISTS adjusted_amount NUMERIC,
ADD COLUMN IF NOT EXISTS paid_amount NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS expense_source VARCHAR(20) DEFAULT 'contract',
ADD COLUMN IF NOT EXISTS expense_category VARCHAR(100),
ADD COLUMN IF NOT EXISTS expense_description TEXT,
ADD COLUMN IF NOT EXISTS vendor_name VARCHAR(255);

UPDATE service_expense
SET expense_source = COALESCE(expense_source, 'contract');

UPDATE service_expense
SET paid_amount = CASE
    WHEN payment_status = '已收款' THEN COALESCE(adjusted_amount, total_amount, 0)
    WHEN payment_status = '部分收款' THEN COALESCE(paid_amount, 0)
    ELSE 0
END
WHERE paid_amount IS NULL OR paid_amount = 0;

ALTER TABLE service_expense
ALTER COLUMN paid_amount SET DEFAULT 0;

CREATE TABLE IF NOT EXISTS bank_ledger_reconciliation_lines (
    id SERIAL PRIMARY KEY,
    bank_ledger_id INTEGER NOT NULL REFERENCES bank_ledger(id) ON DELETE CASCADE,
    target_type VARCHAR(32) NOT NULL,
    target_id INTEGER NOT NULL,
    ar_type VARCHAR(32),
    allocated_amount NUMERIC NOT NULL DEFAULT 0,
    fee_amount NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT bank_ledger_reconciliation_lines_target_type_check
        CHECK (target_type IN ('receivable', 'service_expense'))
);

CREATE INDEX IF NOT EXISTS idx_bank_ledger_reconciliation_lines_ledger_id
    ON bank_ledger_reconciliation_lines(bank_ledger_id);

CREATE INDEX IF NOT EXISTS idx_bank_ledger_reconciliation_lines_target
    ON bank_ledger_reconciliation_lines(target_type, target_id);

CREATE OR REPLACE FUNCTION sync_leasing_ar_from_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_name TEXT;
    v_total_periods INTEGER;
    v_remaining_months INTEGER;
    v_current_start DATE;
    v_current_end DATE;
    v_existing RECORD;
    v_base_amount NUMERIC;
    v_effective_amount NUMERIC;
    v_payment_status payment_status_enum;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS tmp_existing_ar_leasing (
        start_date DATE,
        end_date DATE,
        fee NUMERIC,
        received_amount NUMERIC,
        adjusted_amount NUMERIC
    ) ON COMMIT DROP;

    TRUNCATE tmp_existing_ar_leasing;

    INSERT INTO tmp_existing_ar_leasing (start_date, end_date, fee, received_amount, adjusted_amount)
    SELECT start_date, end_date, fee, received_amount, adjusted_amount
    FROM ar_leasing
    WHERE contract_code = NEW.contract_code;

    DELETE FROM ar_leasing WHERE contract_code = NEW.contract_code;

    IF COALESCE(NEW.status, 'active') <> 'active'
       OR NEW.start_date IS NULL
       OR NEW.monthly_rent IS NULL
       OR NEW.contract_months IS NULL
       OR COALESCE(NEW.payment_cycle_months, 0) <= 0 THEN
        RETURN NEW;
    END IF;

    v_customer_name := COALESCE(
        NULLIF(NEW.customer_name, ''),
        (SELECT name FROM customers WHERE customer_code = NEW.customer_code),
        ''
    );

    v_total_periods := NEW.contract_months / NEW.payment_cycle_months;
    v_remaining_months := MOD(NEW.contract_months, NEW.payment_cycle_months);
    v_current_start := NEW.start_date;

    FOR i IN 1..v_total_periods LOOP
        v_current_end := ((v_current_start + make_interval(months => NEW.payment_cycle_months))::date - 1);

        SELECT fee, received_amount, adjusted_amount
        INTO v_existing
        FROM tmp_existing_ar_leasing
        WHERE start_date = v_current_start AND end_date = v_current_end
        LIMIT 1;

        v_base_amount := NEW.monthly_rent * NEW.payment_cycle_months;
        v_effective_amount := COALESCE(v_existing.adjusted_amount, v_base_amount);

        IF COALESCE(v_existing.received_amount, 0) >= (v_effective_amount + COALESCE(v_existing.fee, 0)) THEN
            v_payment_status := '已收款';
        ELSIF COALESCE(v_existing.received_amount, 0) > 0 THEN
            v_payment_status := '部分收款';
        ELSE
            v_payment_status := '未收';
        END IF;

        INSERT INTO ar_leasing (
            contract_code, customer_code, customer_name, start_date, end_date,
            total_rent, adjusted_amount, fee, received_amount, payment_status
        ) VALUES (
            NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
            v_base_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
            COALESCE(v_existing.received_amount, 0), v_payment_status
        );

        v_current_start := (v_current_start + make_interval(months => NEW.payment_cycle_months))::date;
    END LOOP;

    IF v_remaining_months > 0 THEN
        v_current_end := ((v_current_start + make_interval(months => v_remaining_months))::date - 1);

        SELECT fee, received_amount, adjusted_amount
        INTO v_existing
        FROM tmp_existing_ar_leasing
        WHERE start_date = v_current_start AND end_date = v_current_end
        LIMIT 1;

        v_base_amount := NEW.monthly_rent * v_remaining_months;
        v_effective_amount := COALESCE(v_existing.adjusted_amount, v_base_amount);

        IF COALESCE(v_existing.received_amount, 0) >= (v_effective_amount + COALESCE(v_existing.fee, 0)) THEN
            v_payment_status := '已收款';
        ELSIF COALESCE(v_existing.received_amount, 0) > 0 THEN
            v_payment_status := '部分收款';
        ELSE
            v_payment_status := '未收';
        END IF;

        INSERT INTO ar_leasing (
            contract_code, customer_code, customer_name, start_date, end_date,
            total_rent, adjusted_amount, fee, received_amount, payment_status
        ) VALUES (
            NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
            v_base_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
            COALESCE(v_existing.received_amount, 0), v_payment_status
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION sync_buyout_ar_from_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_name TEXT;
    v_existing RECORD;
    v_effective_amount NUMERIC;
    v_payment_status payment_status_enum;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS tmp_existing_ar_buyout (
        deal_date DATE,
        fee NUMERIC,
        received_amount NUMERIC,
        adjusted_amount NUMERIC
    ) ON COMMIT DROP;

    TRUNCATE tmp_existing_ar_buyout;

    INSERT INTO tmp_existing_ar_buyout (deal_date, fee, received_amount, adjusted_amount)
    SELECT deal_date, fee, received_amount, adjusted_amount
    FROM ar_buyout
    WHERE contract_code = NEW.contract_code;

    DELETE FROM ar_buyout WHERE contract_code = NEW.contract_code;

    IF COALESCE(NEW.status, 'active') <> 'active'
       OR NEW.deal_date IS NULL
       OR NEW.deal_amount IS NULL THEN
        RETURN NEW;
    END IF;

    v_customer_name := COALESCE(
        NULLIF(NEW.customer_name, ''),
        (SELECT name FROM customers WHERE customer_code = NEW.customer_code),
        ''
    );

    SELECT fee, received_amount, adjusted_amount
    INTO v_existing
    FROM tmp_existing_ar_buyout
    WHERE deal_date = NEW.deal_date
    LIMIT 1;

    v_effective_amount := COALESCE(v_existing.adjusted_amount, NEW.deal_amount);

    IF COALESCE(v_existing.received_amount, 0) >= (v_effective_amount + COALESCE(v_existing.fee, 0)) THEN
        v_payment_status := '已收款';
    ELSIF COALESCE(v_existing.received_amount, 0) > 0 THEN
        v_payment_status := '部分收款';
    ELSE
        v_payment_status := '未收';
    END IF;

    INSERT INTO ar_buyout (
        contract_code, customer_code, customer_name, deal_date,
        total_amount, adjusted_amount, fee, received_amount, payment_status
    ) VALUES (
        NEW.contract_code, NEW.customer_code, v_customer_name, NEW.deal_date,
        NEW.deal_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
        COALESCE(v_existing.received_amount, 0), v_payment_status
    );

    RETURN NEW;
END;
$$;
