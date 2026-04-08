UPDATE contracts_leasing AS c
SET monthly_rent = c.monthly_rent
WHERE COALESCE(c.status, 'active') = 'active'
  AND c.monthly_rent IS NOT NULL
  AND c.contract_months IS NOT NULL
  AND COALESCE(c.payment_cycle_months, 0) > 0
  AND NOT EXISTS (
      SELECT 1
      FROM ar_leasing AS a
      WHERE a.contract_code = c.contract_code
  );


UPDATE contracts_buyout AS c
SET deal_amount = c.deal_amount
WHERE COALESCE(c.status, 'active') = 'active'
  AND c.deal_amount IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ar_buyout AS a
      WHERE a.contract_code = c.contract_code
  );
