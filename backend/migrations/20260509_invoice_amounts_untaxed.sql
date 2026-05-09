CREATE OR REPLACE FUNCTION calculate_invoice_receivable_status(
    p_untaxed_amount NUMERIC,
    p_fee NUMERIC,
    p_received_amount NUMERIC,
    p_needs_invoice BOOLEAN
)
RETURNS payment_status_enum
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice_amount NUMERIC;
BEGIN
    v_invoice_amount := COALESCE(p_untaxed_amount, 0);

    IF COALESCE(p_needs_invoice, FALSE) THEN
        v_invoice_amount := v_invoice_amount * 1.05;
    END IF;

    IF COALESCE(p_received_amount, 0) >= (v_invoice_amount + COALESCE(p_fee, 0))
       AND v_invoice_amount > 0 THEN
        RETURN '已收款';
    ELSIF COALESCE(p_received_amount, 0) > 0 THEN
        RETURN '部分收款';
    END IF;

    RETURN '未收';
END;
$$;


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
            v_payment_status := calculate_invoice_receivable_status(
                v_effective_amount,
                COALESCE(v_existing.fee, 0),
                COALESCE(v_existing.received_amount, 0),
                NEW.needs_invoice
            );

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
        v_payment_status := calculate_invoice_receivable_status(
            v_effective_amount,
            COALESCE(v_existing.fee, 0),
            COALESCE(v_existing.received_amount, 0),
            NEW.needs_invoice
        );

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
    v_payment_status := calculate_invoice_receivable_status(
        v_effective_amount,
        COALESCE(v_existing.fee, 0),
        COALESCE(v_existing.received_amount, 0),
        NEW.needs_invoice
    );

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


DROP TRIGGER IF EXISTS trg_sync_leasing_ar_from_contract_change ON contracts_leasing;
CREATE TRIGGER trg_sync_leasing_ar_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, start_date, monthly_rent, payment_cycle_months, contract_months, status, needs_invoice
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION sync_leasing_ar_from_contract();


DROP TRIGGER IF EXISTS trg_sync_buyout_ar_from_contract_change ON contracts_buyout;
CREATE TRIGGER trg_sync_buyout_ar_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, deal_date, deal_amount, status, needs_invoice
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION sync_buyout_ar_from_contract();


CREATE TABLE IF NOT EXISTS app_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS invoice_amount_untaxed_backup_20260509 (
    table_name TEXT NOT NULL,
    row_id INTEGER NOT NULL,
    contract_code TEXT,
    amount_column TEXT NOT NULL,
    amount_before NUMERIC,
    adjusted_amount_before NUMERIC,
    backed_up_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM app_migrations WHERE version = '20260509_invoice_amounts_untaxed'
    ) THEN
        INSERT INTO invoice_amount_untaxed_backup_20260509 (
            table_name, row_id, contract_code, amount_column, amount_before, adjusted_amount_before
        )
        SELECT 'contracts_leasing', id, contract_code, 'monthly_rent', monthly_rent, NULL
        FROM contracts_leasing
        WHERE needs_invoice IS TRUE AND monthly_rent IS NOT NULL;

        INSERT INTO invoice_amount_untaxed_backup_20260509 (
            table_name, row_id, contract_code, amount_column, amount_before, adjusted_amount_before
        )
        SELECT 'contracts_buyout', id, contract_code, 'deal_amount', deal_amount, NULL
        FROM contracts_buyout
        WHERE needs_invoice IS TRUE AND deal_amount IS NOT NULL;

        INSERT INTO invoice_amount_untaxed_backup_20260509 (
            table_name, row_id, contract_code, amount_column, amount_before, adjusted_amount_before
        )
        SELECT 'ar_leasing', al.id, al.contract_code, 'total_rent', al.total_rent, al.adjusted_amount
        FROM ar_leasing al
        JOIN contracts_leasing cl ON cl.contract_code = al.contract_code
        WHERE cl.needs_invoice IS TRUE;

        INSERT INTO invoice_amount_untaxed_backup_20260509 (
            table_name, row_id, contract_code, amount_column, amount_before, adjusted_amount_before
        )
        SELECT 'ar_buyout', ab.id, ab.contract_code, 'total_amount', ab.total_amount, ab.adjusted_amount
        FROM ar_buyout ab
        JOIN contracts_buyout cb ON cb.contract_code = ab.contract_code
        WHERE cb.needs_invoice IS TRUE;

        UPDATE ar_leasing al
        SET adjusted_amount = ROUND((al.adjusted_amount::numeric / 1.05), 2),
            updated_at = CURRENT_TIMESTAMP
        FROM contracts_leasing cl
        WHERE cl.contract_code = al.contract_code
          AND cl.needs_invoice IS TRUE
          AND al.adjusted_amount IS NOT NULL;

        UPDATE ar_buyout ab
        SET adjusted_amount = ROUND((ab.adjusted_amount::numeric / 1.05), 2),
            updated_at = CURRENT_TIMESTAMP
        FROM contracts_buyout cb
        WHERE cb.contract_code = ab.contract_code
          AND cb.needs_invoice IS TRUE
          AND ab.adjusted_amount IS NOT NULL;

        UPDATE contracts_leasing
        SET monthly_rent = ROUND((monthly_rent::numeric / 1.05), 2),
            updated_at = CURRENT_TIMESTAMP
        WHERE needs_invoice IS TRUE
          AND monthly_rent IS NOT NULL;

        UPDATE contracts_buyout
        SET deal_amount = ROUND((deal_amount::numeric / 1.05), 2),
            updated_at = CURRENT_TIMESTAMP
        WHERE needs_invoice IS TRUE
          AND deal_amount IS NOT NULL;

        INSERT INTO app_migrations (version)
        VALUES ('20260509_invoice_amounts_untaxed');
    END IF;
END;
$$;
