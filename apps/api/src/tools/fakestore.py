"""Thin HTTP client for the public FakeStore API (https://fakestoreapi.com).

FakeStore does not expose a true order-status endpoint. We map the domain
concept of an "order" onto FakeStore's ``/carts`` resource, which is the closest
practical analogue (it links a user to a list of purchased products with a date).
``get_order_status`` therefore fetches the cart and derives a deterministic,
synthetic fulfillment status from the cart id so the demo behaves predictably.

All network access goes through ``httpx`` with the timeout from settings. Each
function returns a plain ``dict`` (never raises for a normal 404/timeout) so the
agent can reason over structured results and the audit trail stays clean.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.config import settings

# Synthetic status wheel — deterministic mapping documented above.
_STATUS_WHEEL = ["processing", "shipped", "in_transit", "delivered"]


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.fakestore_base_url,
        timeout=settings.http_timeout_seconds,
    )


def _derive_status(cart_id: int) -> str:
    return _STATUS_WHEEL[cart_id % len(_STATUS_WHEEL)]


def get_order_status(order_id: str | int) -> dict[str, Any]:
    """Return a synthetic order status derived from a FakeStore cart.

    Args:
        order_id: cart id used as the order identifier.
    """
    try:
        oid = int(str(order_id).strip())
    except (TypeError, ValueError):
        return {"error": "invalid_order_id", "order_id": str(order_id)}

    try:
        with _client() as client:
            resp = client.get(f"/carts/{oid}")
            if resp.status_code == 404 or resp.text.strip() in ("", "null"):
                return {"error": "order_not_found", "order_id": oid}
            resp.raise_for_status()
            cart = resp.json()
    except httpx.HTTPError as exc:
        return {"error": "http_error", "detail": str(exc), "order_id": oid}

    if not cart:
        return {"error": "order_not_found", "order_id": oid}

    products = cart.get("products", [])
    return {
        "order_id": oid,
        "status": _derive_status(oid),
        "user_id": cart.get("userId"),
        "order_date": cart.get("date"),
        "item_count": sum(p.get("quantity", 0) for p in products),
        "products": products,
        "note": "status is a demo mapping over FakeStore /carts (no real fulfillment API)",
    }


def get_product(product_id: str | int) -> dict[str, Any]:
    """Fetch a single product by id from FakeStore ``/products/{id}``."""
    try:
        pid = int(str(product_id).strip())
    except (TypeError, ValueError):
        return {"error": "invalid_product_id", "product_id": str(product_id)}

    try:
        with _client() as client:
            resp = client.get(f"/products/{pid}")
            if resp.status_code == 404 or resp.text.strip() in ("", "null"):
                return {"error": "product_not_found", "product_id": pid}
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        return {"error": "http_error", "detail": str(exc), "product_id": pid}


def search_products(query: str = "", category: str | None = None) -> dict[str, Any]:
    """Search the FakeStore catalog.

    FakeStore has no search endpoint, so we fetch the catalog (optionally scoped
    to a category via ``/products/category/{category}``) and filter client-side
    on title/description.
    """
    path = f"/products/category/{category}" if category else "/products"
    try:
        with _client() as client:
            resp = client.get(path)
            resp.raise_for_status()
            products = resp.json() or []
    except httpx.HTTPError as exc:
        return {"error": "http_error", "detail": str(exc), "query": query}

    q = (query or "").strip().lower()
    if q:
        products = [
            p
            for p in products
            if q in str(p.get("title", "")).lower() or q in str(p.get("description", "")).lower()
        ]

    trimmed = [
        {
            "id": p.get("id"),
            "title": p.get("title"),
            "price": p.get("price"),
            "category": p.get("category"),
        }
        for p in products[:10]
    ]
    return {"query": query, "category": category, "count": len(trimmed), "results": trimmed}
