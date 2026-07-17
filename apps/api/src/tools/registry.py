"""Tool registry = the allowlist.

Only tools present in ``ALLOWLIST`` may ever be executed. The researcher node
dispatches exclusively through :func:`dispatch_tool`, which refuses anything not
in the registry and returns a ``blocked`` audit record instead of raising.

Each tool also ships a JSON-schema definition (``TOOL_SCHEMAS``) in the shape
expected by OpenAI-style tool calling, so the same source of truth drives both
what the model is *told* it can call and what it is *allowed* to call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.constants import ToolStatus
from src.tools.fakestore import get_order_status, get_product, search_products

# name -> callable. Membership here is the security boundary.
ALLOWLIST: dict[str, Callable[..., dict[str, Any]]] = {
    "get_order_status": get_order_status,
    "get_product": get_product,
    "search_products": search_products,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": (
                "Look up the fulfillment status of a customer order by its order id. "
                "Backed by FakeStore carts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order identifier (numeric).",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Fetch details for a single product by its numeric id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product identifier (numeric).",
                    }
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog by keyword and optional category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search for."},
                    "category": {
                        "type": "string",
                        "description": "Optional category filter.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def is_allowed(name: str) -> bool:
    return name in ALLOWLIST


def dispatch_tool(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Execute an allowlisted tool and return a structured audit record.

    Returns a dict with keys ``tool_name``, ``args``, ``result``, ``status``.
    Off-allowlist names are never executed — they return ``status="blocked"``.
    """
    args = args or {}
    if not is_allowed(name):
        return {
            "tool_name": name,
            "args": args,
            "result": {"error": "tool_not_allowlisted"},
            "status": ToolStatus.BLOCKED.value,
        }

    func = ALLOWLIST[name]
    try:
        result = func(**args)
    except TypeError as exc:
        return {
            "tool_name": name,
            "args": args,
            "result": {"error": "bad_arguments", "detail": str(exc)},
            "status": ToolStatus.ERROR.value,
        }
    except Exception as exc:  # noqa: BLE001 - never let a tool crash the graph
        return {
            "tool_name": name,
            "args": args,
            "result": {"error": "tool_exception", "detail": str(exc)},
            "status": ToolStatus.ERROR.value,
        }

    status = ToolStatus.OK.value
    if isinstance(result, dict) and result.get("error"):
        status = ToolStatus.ERROR.value
    return {"tool_name": name, "args": args, "result": result, "status": status}
