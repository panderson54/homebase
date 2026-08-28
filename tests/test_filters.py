from decimal import Decimal

from app import _currency, _phonefmt


class TestCurrencyFilter:
    def test_formats_with_commas(self):
        assert _currency(Decimal('1234.5')) == '$1,234.50'

    def test_none_returns_empty_string(self):
        assert _currency(None) == ''

    def test_small_amount(self):
        assert _currency(Decimal('20')) == '$20.00'


class TestPhoneFilter:
    def test_formats_ten_digit_number(self):
        assert _phonefmt('5551234567') == '(555) 123-4567'

    def test_formats_number_with_punctuation(self):
        assert _phonefmt('555-123-4567') == '(555) 123-4567'

    def test_formats_eleven_digit_number_with_country_code(self):
        assert _phonefmt('15551234567') == '(555) 123-4567'

    def test_leaves_non_us_length_unchanged(self):
        assert _phonefmt('12345') == '12345'

    def test_blank_returns_empty_string(self):
        assert _phonefmt('') == ''
        assert _phonefmt(None) == ''
