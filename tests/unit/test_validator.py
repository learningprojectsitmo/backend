from __future__ import annotations

import pytest

from src.util.validator import NameValidator


class TestNameValidator:
    def test_should_accept_cyrillic_names(self):
        # given
        value = "Анна-Мария Иванова"

        # when
        result = NameValidator.validate_name(value)

        # then
        assert result == value

    def test_should_accept_latin_foreign_names(self):
        # given / when / then
        assert NameValidator.validate_name("Jean-Luc") == "Jean-Luc"
        assert NameValidator.validate_name("O'Brien") == "O'Brien"
        assert NameValidator.validate_name("Edu Flow") == "Edu Flow"

    def test_should_trim_surrounding_spaces(self):
        # given
        value = "  Иван  "

        # when / then
        assert NameValidator.validate_name(value) == "Иван"

    def test_should_reject_digits(self):
        # given / when / then
        with pytest.raises(ValueError):
            NameValidator.validate_name("Ivan123")

    def test_should_reject_symbols(self):
        # given / when / then
        with pytest.raises(ValueError):
            NameValidator.validate_name("Ivan@Smith")

    def test_should_reject_empty_required(self):
        # given / when / then
        with pytest.raises(ValueError):
            NameValidator.validate_name("   ", "Имя")

    def test_optional_field_may_be_empty(self):
        # given / when / then
        assert NameValidator.validate_name_optional("") is None
        assert NameValidator.validate_name_optional(None) is None

    def test_optional_field_validates_when_provided(self):
        # given / when / then
        assert NameValidator.validate_name_optional("Петрович") == "Петрович"
        with pytest.raises(ValueError):
            NameValidator.validate_name_optional("Петр1")
