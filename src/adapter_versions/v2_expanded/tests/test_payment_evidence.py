import pytest

from integrations.lite_agent.context_projection import _financial_amount_hint


@pytest.mark.parametrize('text', [
    'Units\tRequested\tApproved\nTotal\t10\t8',
    'Total\n10\t8',
    'Subtotal\t10\t8\nTax\t1\t0.8',
])
def test_multiple_numeric_columns_are_not_one_payment(text):
    assert _financial_amount_hint(text) is None


@pytest.mark.parametrize('text,expected', [
    ('Subtotal 10.00\nTax 0.80\nTOTAL $10.80', 10.8),
    ('AMOUNT DUE\n$25.50', 25.5),
    ('Subtotal 10.00\nTax 0.80', 10.8),
])
def test_unambiguous_receipt_payment_is_preserved(text, expected):
    assert _financial_amount_hint(text)['amount'] == expected
