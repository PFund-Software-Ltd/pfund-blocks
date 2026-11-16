from __future__ import annotations

import copy
import pickle
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field, ValidationError

from pfund_blocks.entities.products.product_base import BaseProduct
from pfund_blocks.entities.trades.quantity import Quantity


def create_product(basis: str) -> BaseProduct:
    return BaseProduct(
        source="BYBIT",
        basis=basis,  # ty: ignore[invalid-argument-type]
        symbol="BTCUSD",
    )


# a product with a contract multiplier, e.g. one S&P 500 future is worth 50 index units
class MultiplierProduct(BaseProduct):
    multiplier: Decimal


class Model(BaseModel):
    quantity: Quantity = Field(gt=0)


class TestArithmetic:
    @pytest.mark.parametrize(
        "result",
        [
            Quantity("2") + Quantity("1"),
            Quantity("2") + 1,
            1 + Quantity("2"),
            Quantity("2") - 1,
            1 - Quantity("2"),
            Quantity("2") * 3,
            3 * Quantity("2"),
            Quantity("2") / 4,
            4 / Quantity("2"),
            -Quantity("2"),
            +Quantity("2"),
            abs(Quantity("-2")),
            sum([Quantity("1"), Quantity("2")]),
        ],
    )
    def test_stays_quantity(self, result: Decimal):
        assert isinstance(result, Quantity)

    def test_values(self):
        assert Quantity("2") + Decimal("0.5") == Decimal("2.5")
        assert 1 - Quantity("2") == Decimal("-1")
        assert 4 / Quantity("2") == Decimal("2")
        assert abs(Quantity("-2")) == Decimal("2")

    def test_unsupported_operand_raises(self):
        with pytest.raises(TypeError):
            Quantity("2") + 1.5

    def test_is_a_decimal(self):
        quantity = Quantity("1.5")
        assert isinstance(quantity, Decimal)
        assert quantity == Decimal("1.5")
        assert hash(quantity) == hash(Decimal("1.5"))

    def test_survives_pickle_and_copy(self):
        quantity = Quantity("1.5")
        for copied in (pickle.loads(pickle.dumps(quantity)), copy.deepcopy(quantity)):
            assert isinstance(copied, Quantity)
            assert copied == quantity


class TestPydantic:
    @pytest.mark.parametrize("value", ["1.5", 1.5, Decimal("1.5")])
    def test_validates_into_quantity(self, value: str | float | Decimal):
        model = Model(quantity=value)
        assert isinstance(model.quantity, Quantity)
        assert model.quantity == Decimal("1.5")

    def test_field_constraint_applies(self):
        with pytest.raises(ValidationError, match="greater_than"):
            Model(quantity=Quantity("0"))

    def test_invalid_value_is_rejected(self):
        with pytest.raises(ValidationError, match="decimal_parsing"):
            Model(quantity="abc")

    def test_json_round_trip(self):
        dumped = Model(quantity=Quantity("1.5")).model_dump_json()
        assert dumped == '{"quantity":"1.5"}'
        model = Model.model_validate_json(dumped)
        assert isinstance(model.quantity, Quantity)
        assert model.quantity == Decimal("1.5")


class TestConversion:
    def test_linear(self):
        product = create_product("BTC_USDT_PERP")
        quantity = Quantity("2")
        # price is ignored for base, used for quote
        assert quantity.to_base(product, Decimal("100")) == Decimal("2")
        assert quantity.to_quote(product, Decimal("100")) == Decimal("200")

    def test_inverse(self):
        product = create_product("BTC_USD_IPERP")
        quantity = Quantity("200")  # 200 USD worth of contracts
        # price is used for base, ignored for quote
        assert quantity.to_base(product, Decimal("100")) == Decimal("2")
        assert quantity.to_quote(product, Decimal("100")) == Decimal("200")

    @pytest.mark.parametrize("basis", ["BTC_USDT_PERP", "BTC_USD_IPERP"])
    def test_base_and_quote_reconcile(self, basis: str):
        product = create_product(basis)
        quantity, price = Quantity("3"), Decimal("150")
        base = quantity.to_base(product, price)
        assert quantity.to_quote(product, price) == base * price

    def test_multiplier(self):
        product = MultiplierProduct(
            source="CME",
            basis="ES_USD_FUT",  # ty: ignore[invalid-argument-type]
            symbol="ES",
            multiplier=Decimal("50"),
        )
        quantity = Quantity("2")
        assert quantity.to_base(product, Decimal("5000")) == Decimal("100")
        assert quantity.to_quote(product, Decimal("5000")) == Decimal("500000")

    def test_short_quantity_keeps_sign(self):
        product = create_product("BTC_USDT_PERP")
        assert Quantity("-2").to_quote(product, Decimal("100")) == Decimal("-200")
