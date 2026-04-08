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
BEGIN
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

        INSERT INTO ar_leasing (
            contract_code, customer_code, customer_name, start_date, end_date,
            total_rent, fee, received_amount, payment_status
        ) VALUES (
            NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
            NEW.monthly_rent * NEW.payment_cycle_months, 0, 0, '未收'
        );

        v_current_start := (v_current_start + make_interval(months => NEW.payment_cycle_months))::date;
    END LOOP;

    IF v_remaining_months > 0 THEN
        v_current_end := ((v_current_start + make_interval(months => v_remaining_months))::date - 1);

        INSERT INTO ar_leasing (
            contract_code, customer_code, customer_name, start_date, end_date,
            total_rent, fee, received_amount, payment_status
        ) VALUES (
            NEW.contract_code, NEW.customer_code, v_customer_name, v_current_start, v_current_end,
            NEW.monthly_rent * v_remaining_months, 0, 0, '未收'
        );
    END IF;

    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION cleanup_leasing_ar_before_contract_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM ar_leasing WHERE contract_code = OLD.contract_code;
    RETURN COALESCE(NEW, OLD);
END;
$$;


CREATE OR REPLACE FUNCTION sync_buyout_ar_from_contract()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_customer_name TEXT;
BEGIN
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

    INSERT INTO ar_buyout (
        contract_code, customer_code, customer_name, deal_date,
        total_amount, fee, received_amount, payment_status
    ) VALUES (
        NEW.contract_code, NEW.customer_code, v_customer_name, NEW.deal_date,
        NEW.deal_amount, 0, 0, '未收'
    );

    RETURN NEW;
END;
$$;


CREATE OR REPLACE FUNCTION cleanup_buyout_ar_before_contract_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM ar_buyout WHERE contract_code = OLD.contract_code;
    RETURN COALESCE(NEW, OLD);
END;
$$;


DROP TRIGGER IF EXISTS trg_cleanup_leasing_ar_before_contract_change ON contracts_leasing;
CREATE TRIGGER trg_cleanup_leasing_ar_before_contract_change
BEFORE UPDATE OF contract_code OR DELETE
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION cleanup_leasing_ar_before_contract_change();


DROP TRIGGER IF EXISTS trg_sync_leasing_ar_from_contract_delete ON contracts_leasing;
DROP TRIGGER IF EXISTS trg_sync_leasing_ar_from_contract_change ON contracts_leasing;
CREATE TRIGGER trg_sync_leasing_ar_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, start_date, monthly_rent, payment_cycle_months, contract_months, status
ON contracts_leasing
FOR EACH ROW
EXECUTE FUNCTION sync_leasing_ar_from_contract();


DROP TRIGGER IF EXISTS trg_cleanup_buyout_ar_before_contract_change ON contracts_buyout;
CREATE TRIGGER trg_cleanup_buyout_ar_before_contract_change
BEFORE UPDATE OF contract_code OR DELETE
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION cleanup_buyout_ar_before_contract_change();


DROP TRIGGER IF EXISTS trg_sync_buyout_ar_from_contract_delete ON contracts_buyout;
DROP TRIGGER IF EXISTS trg_sync_buyout_ar_from_contract_change ON contracts_buyout;
CREATE TRIGGER trg_sync_buyout_ar_from_contract_change
AFTER INSERT OR UPDATE OF contract_code, customer_code, customer_name, deal_date, deal_amount, status
ON contracts_buyout
FOR EACH ROW
EXECUTE FUNCTION sync_buyout_ar_from_contract();
