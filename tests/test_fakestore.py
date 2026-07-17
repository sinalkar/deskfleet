"""FakeStore tool unit tests — HTTP is stubbed, no network required."""

from __future__ import annotations

import httpx
from src.tools import fakestore


class _StubResponse:
    def __init__(self, status_code=200, json_data=None, text="{}"):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _StubClient:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, path):
        return self._response


def _patch_client(monkeypatch, response):
    monkeypatch.setattr(fakestore, "_client", lambda: _StubClient(response))


def test_get_order_status_maps_cart_to_status(monkeypatch):
    cart = {
        "id": 3,
        "userId": 7,
        "date": "2020-03-01",
        "products": [{"productId": 1, "quantity": 2}],
    }
    _patch_client(monkeypatch, _StubResponse(200, cart, text="{...}"))
    result = fakestore.get_order_status("3")
    assert result["order_id"] == 3
    assert result["status"] in {"processing", "shipped", "in_transit", "delivered"}
    assert result["item_count"] == 2
    assert "note" in result  # documents the demo mapping


def test_get_order_status_not_found(monkeypatch):
    _patch_client(monkeypatch, _StubResponse(200, None, text="null"))
    assert fakestore.get_order_status("999")["error"] == "order_not_found"


def test_get_order_status_invalid_id():
    assert fakestore.get_order_status("abc")["error"] == "invalid_order_id"


def test_get_product(monkeypatch):
    _patch_client(monkeypatch, _StubResponse(200, {"id": 1, "title": "T-Shirt"}, text="{...}"))
    assert fakestore.get_product("1")["title"] == "T-Shirt"


def test_search_products_filters_by_query(monkeypatch):
    catalog = [
        {"id": 1, "title": "Blue Shirt", "price": 10, "category": "clothing", "desc": "cotton"},
        {"id": 2, "title": "Red Mug", "price": 5, "category": "home", "desc": "ceramic"},
    ]
    _patch_client(monkeypatch, _StubResponse(200, catalog, text="[...]"))
    result = fakestore.search_products(query="shirt")
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Blue Shirt"
