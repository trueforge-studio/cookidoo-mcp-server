# Cookidoo MCP Server + Web UI

An MCP server for the Cookidoo (Thermomix) platform with a simple web interface.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (optional, for MCP stdio mode):
```
COOKIDOO_EMAIL=your@email.com
COOKIDOO_PASSWORD=yourpassword
```

## Usage

### Option 1: Web UI (recommended for interactive use)

```bash
python bridge_server.py
```

Open http://localhost:8080 in your browser. Enter your Cookidoo credentials and click Connect.

### Option 2: MCP stdio server (for AI assistants like Claude)

```bash
python mcp_server.py
```

Or configure in your MCP client (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cookidoo": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "COOKIDOO_EMAIL": "your@email.com",
        "COOKIDOO_PASSWORD": "yourpassword",
        "COOKIDOO_COUNTRY": "DE",
        "COOKIDOO_LANGUAGE": "de-DE"
      }
    }
  }
}
```

### Run the MCP server in Docker

Copy `.env.mcp.example` to `.env.mcp` and enter your Cookidoo credentials. Keep
that file private; it is ignored by Git and excluded from the image build.

Configure Claude Desktop to start the container through Docker Compose:

```json
{
  "mcpServers": {
    "cookidoo": {
      "command": "docker",
      "args": ["compose", "-f", "/Users/joaquinnunez/cookidoo-mcp/compose.yaml", "run", "--rm", "--no-deps", "cookidoo-mcp"]
    }
  }
}
```

The `cookidoo-mcp` service communicates over stdio and does not publish a port.
It disables OpenTelemetry by default.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_recipes` | Search recipes by keyword |
| `get_recipe_details` | Get full recipe details by ID |
| `get_user_info` | View your account profile |
| `get_active_subscription` | View active subscription status |
| `get_managed_collections` | List managed collections |
| `get_custom_collections` | List custom collections |
| `get_collection_counts` | Count custom and managed collections |
| `create_custom_collection` | Create a custom collection |
| `delete_custom_collection` | Delete a custom collection |
| `add_recipe_to_collection` | Add recipe to a custom collection |
| `remove_recipe_from_collection` | Remove recipe from a custom collection |
| `add_managed_collection` | Add a managed collection |
| `remove_managed_collection` | Remove a managed collection |
| `get_custom_recipe` | View a custom recipe |
| `create_custom_recipe_from` | Copy a recipe as custom (premium may be required) |
| `delete_custom_recipe` | Delete a custom recipe |
| `get_shopping_list` | View recipes in shopping list |
| `get_ingredient_items` | View individual ingredient items |
| `add_recipes_to_shopping_list` | Add recipe ingredients to shopping list |
| `remove_recipes_from_shopping_list` | Remove recipe ingredients from shopping list |
| `add_custom_recipes_to_shopping_list` | Add custom recipe ingredients (premium may be required) |
| `remove_custom_recipes_from_shopping_list` | Remove custom recipe ingredients |
| `get_additional_items` | View manual shopping-list items |
| `add_additional_items` | Add manual shopping-list items |
| `rename_additional_items` | Rename manual shopping-list items |
| `set_additional_items_owned` | Mark manual items owned or not owned |
| `remove_additional_items` | Remove manual shopping-list items |
| `get_planned_recipes` | View meal planner for date range |
| `schedule_recipes` | Add recipes to the meal planner for a date |
| `unschedule_recipe` | Remove a recipe from the meal planner date |
| `schedule_custom_recipes` | Schedule custom recipes (premium may be required) |
| `unschedule_custom_recipe` | Remove custom recipe from calendar |
| `tick_off_items` | Mark ingredient items as owned |
| `untick_items` | Mark ingredient items as not owned |
| `clear_shopping_list` | Clear the entire shopping list |

## Credits

Built on top of the [cookidoo-api](https://github.com/miaucl/cookidoo-api) package by miaucl.
