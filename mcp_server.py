#!/usr/bin/env python3
"""MCP Server for Cookidoo (Thermomix recipe platform)."""

import asyncio
from datetime import date, timedelta
import json
import os
import time
import logging
import re
from typing import Any

import aiohttp
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from cookidoo_api import Cookidoo, CookidooConfig, CookidooLocalizationConfig
from cookidoo_api.types import CookidooAdditionalItem, CookidooIngredientItem
from otel_setup import setup_tracing

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenTelemetry
# ---------------------------------------------------------------------------

tracer = setup_tracing()

# ---------------------------------------------------------------------------
# Cookidoo Session Management
# ---------------------------------------------------------------------------

class CookidooSession:
    """Manages a persistent Cookidoo API session."""

    def __init__(self):
        self.cookidoo: Cookidoo | None = None
        self.session: aiohttp.ClientSession | None = None
        self._authenticated = False

    async def ensure_connected(self):
        if self._authenticated and self.cookidoo:
            return
        email = os.environ.get("COOKIDOO_EMAIL", "")
        password = os.environ.get("COOKIDOO_PASSWORD", "")
        country = os.environ.get("COOKIDOO_COUNTRY", "DE")
        language = os.environ.get("COOKIDOO_LANGUAGE", "de-DE")

        if not email or not password:
            raise ValueError("COOKIDOO_EMAIL and COOKIDOO_PASSWORD env vars required")

        self.session = aiohttp.ClientSession()
        cfg = CookidooConfig(
            email=email,
            password=password,
            localization=CookidooLocalizationConfig(
                country_code=country,
                language=language,
            ),
        )
        self.cookidoo = Cookidoo(self.session, cfg)
        await self.cookidoo.login()
        self._authenticated = True

    async def close(self):
        if self.session:
            await self.session.close()


cookidoo_session = CookidooSession()

algolia_cache = {"app_id": None, "api_key": None, "index": None, "valid_until": 0}


async def search_recipes_via_algolia(query: str, page: int, country: str) -> dict[str, Any]:
    """Search Cookidoo through the same public Algolia endpoint as the web UI."""
    language = "de-DE"
    now = time.time()
    if not algolia_cache["api_key"] or algolia_cache["valid_until"] <= now:
        config_url = (
            f"https://cookidoo.{country}/search/{language}"
            f"?context=recipes&countries={country}&query=test"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(config_url) as response:
                response.raise_for_status()
                html = await response.text()

        next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
        if not next_data_match:
            raise RuntimeError("Could not find Algolia configuration on Cookidoo")

        props = json.loads(next_data_match.group(1))["props"]["pageProps"]
        algolia_cache.update(
            app_id=props["algoliaAppId"],
            api_key=props["algoliaApiKeyData"]["apiKey"],
            valid_until=props["algoliaApiKeyData"]["validUntil"],
            index=props["algoliaIndices"]["recipes"]["relevance"],
        )

    algolia_url = f"https://{algolia_cache['app_id']}-dsn.algolia.net/1/indexes/{algolia_cache['index']}/query"
    headers = {
        "X-Algolia-Application-Id": algolia_cache["app_id"],
        "X-Algolia-API-Key": algolia_cache["api_key"],
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "page": page,
        "hitsPerPage": 20,
        "filters": f"countries:{country}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(algolia_url, headers=headers, json=payload) as response:
            response.raise_for_status()
            result = await response.json()

    recipes = [
        {
            "id": hit.get("id"),
            "title": hit.get("title"),
            "totalTime": hit.get("totalTime"),
            "difficulty": hit.get("difficulty"),
            "rating": hit.get("rating"),
            "servings": hit.get("servings"),
        }
        for hit in result.get("hits", [])
    ]
    return {
        "recipes": recipes,
        "totalHits": result.get("nbHits", 0),
        "page": result.get("page", 0),
        "totalPages": result.get("nbPages", 0),
    }


def json_text(value: Any) -> str:
    def default(item: Any) -> Any:
        if hasattr(item, "__dict__"):
            return {key: value for key, value in vars(item).items() if not key.startswith("_")}
        raise TypeError(f"Cannot serialize {type(item).__name__}")

    return json.dumps(value, default=default, indent=2)

# ---------------------------------------------------------------------------
# MCP Server Definition
# ---------------------------------------------------------------------------

app = Server("cookidoo-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_recipes",
            description="Search for recipes on Cookidoo by query string.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for recipes"},
                    "page": {"type": "integer", "description": "Page number (0-indexed)", "default": 0},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_recipe_details",
            description="Get full details of a specific recipe by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "The Cookidoo recipe ID"},
                },
                "required": ["recipe_id"],
            },
        ),
        Tool(
            name="get_user_info",
            description="Get the Cookidoo account profile.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_active_subscription",
            description="Get the active Cookidoo subscription, if any.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_managed_collections",
            description="Get the user's recipe collections / lists.",
            inputSchema={"type": "object", "properties": {"page": {"type": "integer", "default": 0}}},
        ),
        Tool(
            name="add_recipe_to_collection",
            description="Add a recipe to one of the user's collections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "Recipe ID to add"},
                    "collection_id": {"type": "string", "description": "Target collection ID"},
                },
                "required": ["recipe_id", "collection_id"],
            },
        ),
        Tool(
            name="get_custom_collections",
            description="List the user's custom recipe collections.",
            inputSchema={"type": "object", "properties": {"page": {"type": "integer", "default": 0}}},
        ),
        Tool(
            name="get_collection_counts",
            description="Get total custom and managed collection counts.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="create_custom_collection",
            description="Create a custom recipe collection.",
            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        ),
        Tool(
            name="delete_custom_collection",
            description="Delete a custom recipe collection.",
            inputSchema={"type": "object", "properties": {"collection_id": {"type": "string"}}, "required": ["collection_id"]},
        ),
        Tool(
            name="remove_recipe_from_collection",
            description="Remove a recipe from a custom collection.",
            inputSchema={"type": "object", "properties": {"collection_id": {"type": "string"}, "recipe_id": {"type": "string"}}, "required": ["collection_id", "recipe_id"]},
        ),
        Tool(
            name="add_managed_collection",
            description="Add a Cookidoo managed collection to the account.",
            inputSchema={"type": "object", "properties": {"collection_id": {"type": "string"}}, "required": ["collection_id"]},
        ),
        Tool(
            name="remove_managed_collection",
            description="Remove a managed collection from the account.",
            inputSchema={"type": "object", "properties": {"collection_id": {"type": "string"}}, "required": ["collection_id"]},
        ),
        Tool(
            name="get_custom_recipe",
            description="Get a custom recipe by ID.",
            inputSchema={"type": "object", "properties": {"recipe_id": {"type": "string"}}, "required": ["recipe_id"]},
        ),
        Tool(
            name="create_custom_recipe_from",
            description="Create a custom recipe by copying a Cookidoo recipe. May require a premium subscription.",
            inputSchema={"type": "object", "properties": {"recipe_id": {"type": "string"}, "serving_size": {"type": "integer", "minimum": 1}}, "required": ["recipe_id", "serving_size"]},
        ),
        Tool(
            name="delete_custom_recipe",
            description="Delete a custom recipe.",
            inputSchema={"type": "object", "properties": {"recipe_id": {"type": "string"}}, "required": ["recipe_id"]},
        ),
        Tool(
            name="get_shopping_list",
            description="Get the current shopping list items.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_ingredient_items",
            description="List individual ingredient items in the shopping list.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_recipes_to_shopping_list",
            description="Add recipe ingredients to the shopping list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recipe_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recipe IDs to add to shopping list",
                    },
                },
                "required": ["recipe_ids"],
            },
        ),
        Tool(
            name="remove_recipes_from_shopping_list",
            description="Remove ingredient items belonging to Cookidoo recipes from the shopping list.",
            inputSchema={"type": "object", "properties": {"recipe_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["recipe_ids"]},
        ),
        Tool(
            name="add_custom_recipes_to_shopping_list",
            description="Add ingredient items for custom recipes to the shopping list. May require premium.",
            inputSchema={"type": "object", "properties": {"recipe_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["recipe_ids"]},
        ),
        Tool(
            name="remove_custom_recipes_from_shopping_list",
            description="Remove ingredient items belonging to custom recipes from the shopping list.",
            inputSchema={"type": "object", "properties": {"recipe_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["recipe_ids"]},
        ),
        Tool(
            name="get_additional_items",
            description="List manually added shopping-list items.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_additional_items",
            description="Add manual items to the shopping list.",
            inputSchema={"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}}, "required": ["names"]},
        ),
        Tool(
            name="rename_additional_items",
            description="Rename manually added shopping-list items.",
            inputSchema={"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}, "required": ["id", "name"]}}}, "required": ["items"]},
        ),
        Tool(
            name="set_additional_items_owned",
            description="Mark manually added shopping-list items as owned or not owned.",
            inputSchema={"type": "object", "properties": {"item_ids": {"type": "array", "items": {"type": "string"}}, "is_owned": {"type": "boolean"}}, "required": ["item_ids", "is_owned"]},
        ),
        Tool(
            name="remove_additional_items",
            description="Remove manually added shopping-list items.",
            inputSchema={"type": "object", "properties": {"item_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["item_ids"]},
        ),
        Tool(
            name="get_planned_recipes",
            description="Get recipes planned on the meal planner / calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                },
                "required": ["start_date", "end_date"],
            },
        ),
        Tool(
            name="schedule_recipes",
            description="Schedule one or more Cookidoo recipes for a specific date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date to schedule recipes for (YYYY-MM-DD)"},
                    "recipe_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Recipe IDs to add to the meal planner",
                    },
                },
                "required": ["date", "recipe_ids"],
            },
        ),
        Tool(
            name="unschedule_recipe",
            description="Remove a Cookidoo recipe from a specific calendar date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Scheduled date (YYYY-MM-DD)"},
                    "recipe_id": {"type": "string", "description": "Recipe ID to remove from the meal planner"},
                },
                "required": ["date", "recipe_id"],
            },
        ),
        Tool(
            name="schedule_custom_recipes",
            description="Schedule custom recipes for a date. May require premium.",
            inputSchema={"type": "object", "properties": {"date": {"type": "string", "description": "Date (YYYY-MM-DD)"}, "recipe_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["date", "recipe_ids"]},
        ),
        Tool(
            name="unschedule_custom_recipe",
            description="Remove a custom recipe from a calendar date.",
            inputSchema={"type": "object", "properties": {"date": {"type": "string", "description": "Date (YYYY-MM-DD)"}, "recipe_id": {"type": "string"}}, "required": ["date", "recipe_id"]},
        ),
        Tool(
            name="tick_off_items",
            description="Mark shopping list items as bought/owned (tick them off).",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of item IDs to tick off",
                    },
                },
                "required": ["item_ids"],
            },
        ),
        Tool(
            name="untick_items",
            description="Mark shopping list items as not bought/not owned (untick them).",
            inputSchema={
                "type": "object",
                "properties": {
                    "item_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of item IDs to untick",
                    },
                },
                "required": ["item_ids"],
            },
        ),
        Tool(
            name="clear_shopping_list",
            description="Clear the entire shopping list (remove all items).",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------------------------------------------------------------------------
# Tool execution (with per-tool span attributes)
# ---------------------------------------------------------------------------

async def _execute_tool(name: str, arguments: dict[str, Any], cd: Cookidoo) -> list[TextContent]:
    """Run the requested tool and enrich the current span with tool-specific attributes."""
    span = trace.get_current_span()

    if name == "search_recipes":
        country = cd.localization.country_code.lower()
        results = await search_recipes_via_algolia(
            arguments["query"],
            arguments.get("page", 0),
            country,
        )
        span.set_attribute("cookidoo.query", arguments["query"])
        span.set_attribute("cookidoo.page", arguments.get("page", 0))
        span.set_attribute("cookidoo.result_count", results["totalHits"])
        return [TextContent(type="text", text=json_text(results))]

    elif name == "get_recipe_details":
        recipe = await cd.get_recipe_details(arguments["recipe_id"])
        span.set_attribute("cookidoo.recipe_id", arguments["recipe_id"])
        if isinstance(recipe, dict):
            span.set_attribute("cookidoo.recipe_name", str(recipe.get("name", "")))
        return [TextContent(type="text", text=json_text(recipe))]

    elif name == "get_user_info":
        return [TextContent(type="text", text=json_text(await cd.get_user_info()))]

    elif name == "get_active_subscription":
        return [TextContent(type="text", text=json_text(await cd.get_active_subscription()))]

    elif name == "get_managed_collections":
        collections = await cd.get_managed_collections(arguments.get("page", 0))
        span.set_attribute("cookidoo.collection_count", len(collections) if collections else 0)
        return [TextContent(type="text", text=json_text(collections))]

    elif name == "add_recipe_to_collection":
        result = await cd.add_recipes_to_custom_collection(
            arguments["collection_id"],
            [arguments["recipe_id"]],
        )
        span.set_attribute("cookidoo.recipe_id", arguments["recipe_id"])
        span.set_attribute("cookidoo.collection_id", arguments["collection_id"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "get_custom_collections":
        result = await cd.get_custom_collections(arguments.get("page", 0))
        return [TextContent(type="text", text=json_text(result))]

    elif name == "get_collection_counts":
        custom_count, custom_pages = await cd.count_custom_collections()
        managed_count, managed_pages = await cd.count_managed_collections()
        return [TextContent(type="text", text=json_text({
            "custom": {"count": custom_count, "pages": custom_pages},
            "managed": {"count": managed_count, "pages": managed_pages},
        }))]

    elif name == "create_custom_collection":
        result = await cd.add_custom_collection(arguments["name"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "delete_custom_collection":
        await cd.remove_custom_collection(arguments["collection_id"])
        return [TextContent(type="text", text=json_text({"deleted": True}))]

    elif name == "remove_recipe_from_collection":
        result = await cd.remove_recipe_from_custom_collection(
            arguments["collection_id"], arguments["recipe_id"]
        )
        return [TextContent(type="text", text=json_text(result))]

    elif name == "add_managed_collection":
        result = await cd.add_managed_collection(arguments["collection_id"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "remove_managed_collection":
        await cd.remove_managed_collection(arguments["collection_id"])
        return [TextContent(type="text", text=json_text({"deleted": True}))]

    elif name == "get_custom_recipe":
        result = await cd.get_custom_recipe(arguments["recipe_id"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "create_custom_recipe_from":
        result = await cd.add_custom_recipe_from(
            arguments["recipe_id"], arguments["serving_size"]
        )
        return [TextContent(type="text", text=json_text(result))]

    elif name == "delete_custom_recipe":
        await cd.remove_custom_recipe(arguments["recipe_id"])
        return [TextContent(type="text", text=json_text({"deleted": True}))]

    elif name == "get_shopping_list":
        items = await cd.get_shopping_list_recipes()
        span.set_attribute("cookidoo.item_count", len(items) if items else 0)
        return [TextContent(type="text", text=json_text(items))]

    elif name == "get_ingredient_items":
        items = await cd.get_ingredient_items()
        span.set_attribute("cookidoo.item_count", len(items) if items else 0)
        return [TextContent(type="text", text=json_text(items))]

    elif name == "add_recipes_to_shopping_list":
        recipe_ids = arguments["recipe_ids"]
        result = await cd.add_ingredient_items_for_recipes(recipe_ids)
        span.set_attribute("cookidoo.recipe_count", len(recipe_ids))
        span.set_attribute("cookidoo.recipe_ids", ", ".join(recipe_ids))
        return [TextContent(type="text", text=json_text(result))]

    elif name == "remove_recipes_from_shopping_list":
        await cd.remove_ingredient_items_for_recipes(arguments["recipe_ids"])
        return [TextContent(type="text", text=json_text({"removed": True}))]

    elif name == "add_custom_recipes_to_shopping_list":
        result = await cd.add_ingredient_items_for_custom_recipes(arguments["recipe_ids"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "remove_custom_recipes_from_shopping_list":
        await cd.remove_ingredient_items_for_custom_recipes(arguments["recipe_ids"])
        return [TextContent(type="text", text=json_text({"removed": True}))]

    elif name == "get_additional_items":
        return [TextContent(type="text", text=json_text(await cd.get_additional_items()))]

    elif name == "add_additional_items":
        result = await cd.add_additional_items(arguments["names"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "rename_additional_items":
        current_items = {item.id: item for item in await cd.get_additional_items()}
        requested_items = arguments["items"]
        missing_ids = [item["id"] for item in requested_items if item["id"] not in current_items]
        if missing_ids:
            raise ValueError(f"Unknown additional item IDs: {', '.join(missing_ids)}")
        updates = [
            CookidooAdditionalItem(item["id"], item["name"], current_items[item["id"]].is_owned)
            for item in requested_items
        ]
        result = await cd.edit_additional_items(updates)
        return [TextContent(type="text", text=json_text(result))]

    elif name == "set_additional_items_owned":
        current_items = {item.id: item for item in await cd.get_additional_items()}
        item_ids = arguments["item_ids"]
        missing_ids = [item_id for item_id in item_ids if item_id not in current_items]
        if missing_ids:
            raise ValueError(f"Unknown additional item IDs: {', '.join(missing_ids)}")
        updates = [
            CookidooAdditionalItem(item_id, current_items[item_id].name, arguments["is_owned"])
            for item_id in item_ids
        ]
        result = await cd.edit_additional_items_ownership(updates)
        return [TextContent(type="text", text=json_text(result))]

    elif name == "remove_additional_items":
        await cd.remove_additional_items(arguments["item_ids"])
        return [TextContent(type="text", text=json_text({"removed": True}))]

    elif name == "get_planned_recipes":
        start_date = date.fromisoformat(arguments["start_date"])
        end_date = date.fromisoformat(arguments["end_date"])
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        planned = []
        current_date = start_date
        while current_date <= end_date:
            planned.extend(await cd.get_recipes_in_calendar_week(current_date))
            current_date += timedelta(days=7)
        span.set_attribute("cookidoo.start_date", arguments["start_date"])
        span.set_attribute("cookidoo.end_date", arguments["end_date"])
        span.set_attribute("cookidoo.result_count", len(planned) if planned else 0)
        return [TextContent(type="text", text=json_text(planned))]

    elif name == "schedule_recipes":
        scheduled_date = date.fromisoformat(arguments["date"])
        recipe_ids = arguments["recipe_ids"]
        result = await cd.add_recipes_to_calendar(scheduled_date, recipe_ids)
        span.set_attribute("cookidoo.date", arguments["date"])
        span.set_attribute("cookidoo.recipe_count", len(recipe_ids))
        return [TextContent(type="text", text=json_text(result))]

    elif name == "unschedule_recipe":
        scheduled_date = date.fromisoformat(arguments["date"])
        result = await cd.remove_recipe_from_calendar(scheduled_date, arguments["recipe_id"])
        span.set_attribute("cookidoo.date", arguments["date"])
        span.set_attribute("cookidoo.recipe_id", arguments["recipe_id"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "schedule_custom_recipes":
        scheduled_date = date.fromisoformat(arguments["date"])
        result = await cd.add_custom_recipes_to_calendar(scheduled_date, arguments["recipe_ids"])
        return [TextContent(type="text", text=json_text(result))]

    elif name == "unschedule_custom_recipe":
        scheduled_date = date.fromisoformat(arguments["date"])
        result = await cd.remove_custom_recipe_from_calendar(
            scheduled_date, arguments["recipe_id"]
        )
        return [TextContent(type="text", text=json_text(result))]

    elif name == "tick_off_items":
        item_ids = arguments["item_ids"]
        all_items = await cd.get_ingredient_items()
        items_to_update = [
            CookidooIngredientItem(id=item.id, name=item.name, description=item.description, is_owned=True)
            for item in all_items if item.id in item_ids
        ]
        span.set_attribute("cookidoo.requested_count", len(item_ids))
        span.set_attribute("cookidoo.updated_count", len(items_to_update))
        if items_to_update:
            result = await cd.edit_ingredient_items_ownership(items_to_update)
            return [TextContent(type="text", text=json_text({"updated": len(result), "items": result}))]
        return [TextContent(type="text", text=json_text({"updated": 0, "items": []}))]

    elif name == "untick_items":
        item_ids = arguments["item_ids"]
        all_items = await cd.get_ingredient_items()
        items_to_update = [
            CookidooIngredientItem(id=item.id, name=item.name, description=item.description, is_owned=False)
            for item in all_items if item.id in item_ids
        ]
        span.set_attribute("cookidoo.requested_count", len(item_ids))
        span.set_attribute("cookidoo.updated_count", len(items_to_update))
        if items_to_update:
            result = await cd.edit_ingredient_items_ownership(items_to_update)
            return [TextContent(type="text", text=json_text({"updated": len(result), "items": result}))]
        return [TextContent(type="text", text=json_text({"updated": 0, "items": []}))]

    elif name == "clear_shopping_list":
        await cd.clear_shopping_list()
        return [TextContent(type="text", text=json_text({"cleared": True}))]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# call_tool — wraps every tool call in a span
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    start = time.time()

    with tracer.start_as_current_span(
        f"mcp.tool.{name}",
        attributes={
            "mcp.tool.name": name,
            "mcp.server": "cookidoo-mcp",
        },
    ) as span:
        try:
            await cookidoo_session.ensure_connected()
            cd = cookidoo_session.cookidoo

            result = await _execute_tool(name, arguments, cd)

            duration_ms = int((time.time() - start) * 1000)
            span.set_attribute("mcp.tool.duration_ms", duration_ms)
            span.set_attribute("mcp.tool.success", True)
            return result

        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            span.set_attribute("mcp.tool.duration_ms", duration_ms)
            span.set_attribute("mcp.tool.success", False)
            span.set_attribute("error.message", str(e))
            span.set_attribute("error.type", type(e).__name__)
            span.set_status(StatusCode.ERROR, str(e))
            logger.exception("Tool call failed")
            return [TextContent(type="text", text=f"Error: {e}")]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
