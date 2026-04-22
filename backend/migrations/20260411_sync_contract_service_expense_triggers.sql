CREATE OR REPLACE FUNCTION calculate_service_expense_payment_status(
    p_amount NUMERIC,
    p_paid_amount NUMERIC
)
RETURNS payment_status_enum
LANGUAGE plpgsql
AS $$
BEGIN
    IF COALESCE(p_paid_amount, 0) >= COALESCE(p_amount, 0) AND COALESCE(p_amount, 0) > 0 THEN
        RETURN '已收款';
    ELSIF COALESCE(p_paid_amount, 0) > 0 THEN
        RETURN '部分收款';
    END IF;

    RETURN '未收';
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
BEGIN
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
                expense_source
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
                'contract'
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


CREATE OR REPLACE FUNCTION sync_contract_service_expenses(
    p_contract_code TEXT,
    p_customer_code TEXT,
    p_customer_name TEXT,
    p_sales_company_code TEXT,
    p_sales_amount NUMERIC,
    p_service_company_code TEXT,
    p_service_amount NUMERIC,
    p_status TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF COALESCE(p_status, 'active') <> 'active' THEN
        DELETE FROM service_expense
        WHERE contract_code = p_contract_code
          AND COALESCE(expense_source, 'contract') = 'contract';
        RETURN;
    END IF;

    PERFORM sync_single_contract_service_expense(
        p_contract_code,
        p_customer_code,
        p_customer_name,
        '業務',
        p_sales_company_code,
        p_sales_amount
    );

    PERFORM sync_single_contract_service_expense(
        p_contract_code,
        p_customer_code,
        p_customer_name,
        '維護',
        p_service_company_code,
        p_service_amount
    );

    DELETE FROM service_expense
    WHERE contract_code = p_contract_code
      AND COALESCE(expense_source, 'contract') = 'contract'
      AND service_type NOT IN ('業務', '維護');
END;
$$;


CREATE OR REPLACE FUNCTION move_contract_service_expenses_before_code_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE service_expense
    SET contract_code = NEW.contract_code,
        updated_at = CURRENT_TIMESTAMP
    WHERE contract_code = OLD.contract_code
      AND COALESCE(expense_source, 'contract') = 'contract';

    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION cleanup_contract_service_expenses_before_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM service_expense
    WHERE contract_code = OLD.contract_code
      AND COALESCE(expense_source, 'contract') = 'contract';

    RETURN OLD;
END;
$$;


CREATE OR REPLACE FUNCTION sync_leasing_service_expense_from_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_name TEXT;
BEGIN
    v_customer_name := COALESCE(
        NULLIF(NEW.customer_name, ''),
        (SELECT name FROM customers WHERE customer_code = NEW.customer_code),
        ''
    );

    PERFORM sync_contract_service_expenses(
        NEW.contract_code,
        NEW.customer_code,
        v_customer_name,
        NEW.sales_company_code,
        NEW.sales_amount,
        NEW.service_company_code,
        NEW.service_amount,
        NEW.status
    );

    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION sync_buyout_service_expense_from_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_name TEXT;
BEGIN
    v_customer_name := COALESCE(
        NULLIF(NEW.customer_name, ''),
        (SELECT name FROM customers WHERE customer_code = NEW.customer_code),
        ''
    );

    PERFORM sync_contract_service_expenses(
        NEW.contract_code,
        NEW.customer_code,
        v_customer_name,
        NEW.sales_company_code,
        NEW.sales_amount,
        NEW.service_company_code,
        NEW.service_amount,
        NEW.status
    );

    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS trg_move_leasing_service_expense_before_contract_code_change ON contracts_leasing;
CREATE TRIGGER trg_move_leasing_service_expense_before_contract_code_change
BEFORE UPDATE OF contract_code
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION move_contract_service_expenses_before_code_change();


DROP TRIGGER IF EXISTS trg_cleanup_leasing_service_expense_before_contract_delete ON contracts_leasing;
CREATE TRIGGER trg_cleanup_leasing_service_expense_before_contract_delete
BEFORE DELETE
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION cleanup_contract_service_expenses_before_delete();


DROP TRIGGER IF EXISTS trg_sync_leasing_service_expense_from_contract_change ON contracts_leasing;
CREATE TRIGGER trg_sync_leasing_service_expense_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, sales_company_code, sales_amount, service_company_code, service_amount, status
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION sync_leasing_service_expense_from_contract();


DROP TRIGGER IF EXISTS trg_move_buyout_service_expense_before_contract_code_change ON contracts_buyout;
CREATE TRIGGER trg_move_buyout_service_expense_before_contract_code_change
BEFORE UPDATE OF contract_code
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION move_contract_service_expenses_before_code_change();


DROP TRIGGER IF EXISTS trg_cleanup_buyout_service_expense_before_contract_delete ON contracts_buyout;
CREATE TRIGGER trg_cleanup_buyout_service_expense_before_contract_delete
BEFORE DELETE
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION cleanup_contract_service_expenses_before_delete();


DROP TRIGGER IF EXISTS trg_sync_buyout_service_expense_from_contract_change ON contracts_buyout;
CREATE TRIGGER trg_sync_buyout_service_expense_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, sales_company_code, sales_amount, service_company_code, service_amount, status
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION sync_buyout_service_expense_from_contract();


UPDATE contracts_leasing
SET sales_amount = sales_amount
WHERE COALESCE(status, 'active') = 'active'
  AND (
      (sales_company_code IS NOT NULL AND sales_amount IS NOT NULL AND sales_amount > 0)
      OR (service_company_code IS NOT NULL AND service_amount IS NOT NULL AND service_amount > 0)
  );


UPDATE contracts_buyout
SET sales_amount = sales_amount
WHERE COALESCE(status, 'active') = 'active'
  AND (
      (sales_company_code IS NOT NULL AND sales_amount IS NOT NULL AND sales_amount > 0)
      OR (service_company_code IS NOT NULL AND service_amount IS NOT NULL AND service_amount > 0)
  );
