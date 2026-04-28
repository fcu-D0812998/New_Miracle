CREATE OR REPLACE FUNCTION determine_accounting_period(p_date DATE)
RETURNS VARCHAR(20)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_date IS NOT NULL AND p_date < DATE '2026-01-01' THEN
        RETURN 'prior';
    END IF;

    RETURN 'current';
END;
$$;


CREATE OR REPLACE FUNCTION leasing_contract_accounting_period(
    p_start_date DATE,
    p_contract_months INTEGER
)
RETURNS VARCHAR(20)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_end_date DATE;
BEGIN
    IF p_start_date IS NULL THEN
        RETURN 'current';
    END IF;

    IF COALESCE(p_contract_months, 0) <= 0 THEN
        v_end_date := p_start_date;
    ELSE
        v_end_date := ((p_start_date + make_interval(months => p_contract_months))::date - 1);
    END IF;

    RETURN determine_accounting_period(v_end_date);
END;
$$;


CREATE OR REPLACE FUNCTION service_expense_effective_date(
    p_contract_code TEXT,
    p_service_date DATE,
    p_created_at TIMESTAMP WITHOUT TIME ZONE
)
RETURNS DATE
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_contract_date DATE;
BEGIN
    IF p_contract_code IS NOT NULL THEN
        SELECT start_date
        INTO v_contract_date
        FROM contracts_leasing
        WHERE contract_code = p_contract_code
        LIMIT 1;

        IF v_contract_date IS NULL THEN
            SELECT deal_date
            INTO v_contract_date
            FROM contracts_buyout
            WHERE contract_code = p_contract_code
            LIMIT 1;
        END IF;
    END IF;

    RETURN COALESCE(p_service_date, v_contract_date, p_created_at::date, CURRENT_DATE);
END;
$$;


ALTER TABLE contracts_leasing
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);

ALTER TABLE contracts_buyout
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);

ALTER TABLE ar_leasing
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);

ALTER TABLE ar_buyout
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);

ALTER TABLE service_expense
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);

ALTER TABLE bank_ledger
ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20);


UPDATE contracts_leasing
SET accounting_period = leasing_contract_accounting_period(start_date, contract_months);

UPDATE contracts_buyout
SET accounting_period = determine_accounting_period(deal_date);

UPDATE ar_leasing
SET accounting_period = determine_accounting_period(COALESCE(end_date, start_date));

UPDATE ar_buyout
SET accounting_period = determine_accounting_period(deal_date);

UPDATE service_expense
SET accounting_period = determine_accounting_period(
    service_expense_effective_date(contract_code, service_date, created_at)
);

UPDATE bank_ledger
SET accounting_period = determine_accounting_period(txn_date);


ALTER TABLE contracts_leasing
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;

ALTER TABLE contracts_buyout
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;

ALTER TABLE ar_leasing
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;

ALTER TABLE ar_buyout
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;

ALTER TABLE service_expense
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;

ALTER TABLE bank_ledger
ALTER COLUMN accounting_period SET DEFAULT 'current',
ALTER COLUMN accounting_period SET NOT NULL;


ALTER TABLE contracts_leasing
DROP CONSTRAINT IF EXISTS contracts_leasing_accounting_period_check,
ADD CONSTRAINT contracts_leasing_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));

ALTER TABLE contracts_buyout
DROP CONSTRAINT IF EXISTS contracts_buyout_accounting_period_check,
ADD CONSTRAINT contracts_buyout_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));

ALTER TABLE ar_leasing
DROP CONSTRAINT IF EXISTS ar_leasing_accounting_period_check,
ADD CONSTRAINT ar_leasing_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));

ALTER TABLE ar_buyout
DROP CONSTRAINT IF EXISTS ar_buyout_accounting_period_check,
ADD CONSTRAINT ar_buyout_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));

ALTER TABLE service_expense
DROP CONSTRAINT IF EXISTS service_expense_accounting_period_check,
ADD CONSTRAINT service_expense_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));

ALTER TABLE bank_ledger
DROP CONSTRAINT IF EXISTS bank_ledger_accounting_period_check,
ADD CONSTRAINT bank_ledger_accounting_period_check
CHECK (accounting_period IN ('current', 'prior'));


CREATE INDEX IF NOT EXISTS idx_contracts_leasing_accounting_period
    ON contracts_leasing(accounting_period);

CREATE INDEX IF NOT EXISTS idx_contracts_buyout_accounting_period
    ON contracts_buyout(accounting_period);

CREATE INDEX IF NOT EXISTS idx_ar_leasing_accounting_period
    ON ar_leasing(accounting_period);

CREATE INDEX IF NOT EXISTS idx_ar_buyout_accounting_period
    ON ar_buyout(accounting_period);

CREATE INDEX IF NOT EXISTS idx_service_expense_accounting_period
    ON service_expense(accounting_period);

CREATE INDEX IF NOT EXISTS idx_bank_ledger_accounting_period
    ON bank_ledger(accounting_period);


CREATE OR REPLACE FUNCTION set_contracts_leasing_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := leasing_contract_accounting_period(NEW.start_date, NEW.contract_months);
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION set_contracts_buyout_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := determine_accounting_period(NEW.deal_date);
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION set_ar_leasing_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := determine_accounting_period(COALESCE(NEW.end_date, NEW.start_date));
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION set_ar_buyout_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := determine_accounting_period(NEW.deal_date);
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION set_service_expense_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := determine_accounting_period(
        service_expense_effective_date(NEW.contract_code, NEW.service_date, NEW.created_at)
    );
    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION set_bank_ledger_accounting_period()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.accounting_period := determine_accounting_period(NEW.txn_date);
    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS trg_set_contracts_leasing_accounting_period ON contracts_leasing;
CREATE TRIGGER trg_set_contracts_leasing_accounting_period
BEFORE INSERT OR UPDATE
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION set_contracts_leasing_accounting_period();


DROP TRIGGER IF EXISTS trg_set_contracts_buyout_accounting_period ON contracts_buyout;
CREATE TRIGGER trg_set_contracts_buyout_accounting_period
BEFORE INSERT OR UPDATE
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION set_contracts_buyout_accounting_period();


DROP TRIGGER IF EXISTS trg_set_ar_leasing_accounting_period ON ar_leasing;
CREATE TRIGGER trg_set_ar_leasing_accounting_period
BEFORE INSERT OR UPDATE
ON ar_leasing
FOR EACH ROW
EXECUTE FUNCTION set_ar_leasing_accounting_period();


DROP TRIGGER IF EXISTS trg_set_ar_buyout_accounting_period ON ar_buyout;
CREATE TRIGGER trg_set_ar_buyout_accounting_period
BEFORE INSERT OR UPDATE
ON ar_buyout
FOR EACH ROW
EXECUTE FUNCTION set_ar_buyout_accounting_period();


DROP TRIGGER IF EXISTS trg_set_service_expense_accounting_period ON service_expense;
CREATE TRIGGER trg_set_service_expense_accounting_period
BEFORE INSERT OR UPDATE
ON service_expense
FOR EACH ROW
EXECUTE FUNCTION set_service_expense_accounting_period();


DROP TRIGGER IF EXISTS trg_set_bank_ledger_accounting_period ON bank_ledger;
CREATE TRIGGER trg_set_bank_ledger_accounting_period
BEFORE INSERT OR UPDATE
ON bank_ledger
FOR EACH ROW
EXECUTE FUNCTION set_bank_ledger_accounting_period();


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

    IF v_total_periods > 0 THEN
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
                total_rent, adjusted_amount, fee, received_amount, payment_status,
                accounting_period
            ) VALUES (
                NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
                v_base_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
                COALESCE(v_existing.received_amount, 0), v_payment_status,
                determine_accounting_period(v_current_end)
            );

            v_current_start := (v_current_start + make_interval(months => NEW.payment_cycle_months))::date;
        END LOOP;
    END IF;

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
            total_rent, adjusted_amount, fee, received_amount, payment_status,
            accounting_period
        ) VALUES (
            NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
            v_base_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
            COALESCE(v_existing.received_amount, 0), v_payment_status,
            determine_accounting_period(v_current_end)
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
        total_amount, adjusted_amount, fee, received_amount, payment_status,
        accounting_period
    ) VALUES (
        NEW.contract_code, NEW.customer_code, v_customer_name, NEW.deal_date,
        NEW.deal_amount, v_existing.adjusted_amount, COALESCE(v_existing.fee, 0),
        COALESCE(v_existing.received_amount, 0), v_payment_status,
        determine_accounting_period(NEW.deal_date)
    );

    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION sync_single_contract_service_expense(
    p_contract_code TEXT,
    p_customer_code TEXT,
    p_customer_name TEXT,
    p_service_type TEXT,
    p_company_code TEXT,
    p_base_amount NUMERIC
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing RECORD;
    v_effective_amount NUMERIC;
    v_payment_status payment_status_enum;
    v_accounting_period VARCHAR(20);
BEGIN
    v_accounting_period := determine_accounting_period(
        service_expense_effective_date(p_contract_code, NULL, NULL)
    );

    SELECT id, adjusted_amount, paid_amount
    INTO v_existing
    FROM service_expense
    WHERE contract_code = p_contract_code
      AND service_type = p_service_type
      AND COALESCE(expense_source, 'contract') = 'contract'
    ORDER BY id
    LIMIT 1;

    IF v_existing.id IS NOT NULL THEN
        DELETE FROM service_expense
        WHERE contract_code = p_contract_code
          AND service_type = p_service_type
          AND COALESCE(expense_source, 'contract') = 'contract'
          AND id <> v_existing.id;
    END IF;

    IF p_company_code IS NOT NULL
       AND p_base_amount IS NOT NULL
       AND p_base_amount > 0 THEN
        v_effective_amount := COALESCE(v_existing.adjusted_amount, p_base_amount);
        v_payment_status := calculate_service_expense_payment_status(
            v_effective_amount,
            COALESCE(v_existing.paid_amount, 0)
        );

        IF v_existing.id IS NOT NULL THEN
            UPDATE service_expense
            SET customer_code = p_customer_code,
                customer_name = p_customer_name,
                service_type = p_service_type,
                repair_company_code = p_company_code,
                total_amount = p_base_amount,
                adjusted_amount = v_existing.adjusted_amount,
                paid_amount = COALESCE(v_existing.paid_amount, 0),
                payment_status = v_payment_status,
                expense_source = 'contract',
                expense_category = NULL,
                expense_description = NULL,
                vendor_name = NULL,
                accounting_period = v_accounting_period,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = v_existing.id;
        ELSE
            INSERT INTO service_expense (
                contract_code,
                customer_code,
                customer_name,
                service_type,
                repair_company_code,
                total_amount,
                adjusted_amount,
                paid_amount,
                payment_status,
                expense_source,
                accounting_period
            ) VALUES (
                p_contract_code,
                p_customer_code,
                p_customer_name,
                p_service_type,
                p_company_code,
                p_base_amount,
                NULL,
                0,
                '未收',
                'contract',
                v_accounting_period
            );
        END IF;
    ELSE
        DELETE FROM service_expense
        WHERE contract_code = p_contract_code
          AND service_type = p_service_type
          AND COALESCE(expense_source, 'contract') = 'contract';
    END IF;
END;
$$;


DROP TRIGGER IF EXISTS trg_sync_leasing_service_expense_from_contract_change ON contracts_leasing;
CREATE TRIGGER trg_sync_leasing_service_expense_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, start_date, sales_company_code, sales_amount, service_company_code, service_amount, status
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION sync_leasing_service_expense_from_contract();


DROP TRIGGER IF EXISTS trg_sync_buyout_service_expense_from_contract_change ON contracts_buyout;
CREATE TRIGGER trg_sync_buyout_service_expense_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, deal_date, sales_company_code, sales_amount, service_company_code, service_amount, status
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION sync_buyout_service_expense_from_contract();
