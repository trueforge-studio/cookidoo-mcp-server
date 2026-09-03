# Cookidoo MCP Server

An MCP server for the Cookidoo (Thermomix) platform.

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

### MCP stdio server (for AI assistants like Claude)

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
        "COOKIDOO_COUNTRY": "ES",
        "COOKIDOO_LANGUAGE": "es-ES"
      }
    }
  }
}
```

### MCPB bundle for Claude Desktop

This project includes an MCP Bundle (`.mcpb`) manifest that runs the server
without Docker. The bundle asks for Cookidoo email and password during
installation. Country and language are optional and default to `ES` and
`es-ES`; examples such as `DE` / `de-DE` can be entered when needed.

Install the MCPB CLI and create the bundle from this directory:

```bash
npm install -g @anthropic-ai/mcpb
mcpb pack
```

Then open the generated `.mcpb` file with Claude Desktop. It will install the
server and securely store the sensitive password configuration.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_recipes` | Search recipes by keyword, ingredients, rating, or difficulty |
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

### Recipe Search Filters

`search_recipes` accepts these optional filters in addition to `query` and `page`:

| Parameter | Values | Behavior |
|-----------|--------|----------|
| `include_ingredients` | Array of ingredient names in the Cookidoo locale | Every result must include all listed ingredients. |
| `exclude_ingredients` | Array of ingredient names in the Cookidoo locale | Results containing any listed ingredient are omitted. |
| `min_rating` | Number from `0` to `5` | Returns recipes with at least that star rating. |
| `difficulty` | `easy`, `medium`, or `advanced` | Filters by Cookidoo's internal difficulty values. |
| `sort_by` | `relevance`, `name`, `shortest_preparation_time`, `shortest_total_time`, `newest`, `best_rated`, `trending` | Sorts results using Cookidoo's official search indexes. |
| `countries` | Country codes such as `de`, `at`, `ch`, `it` | Limits recipes by country of origin. Defaults to configured country. |
| `languages` | Language codes such as `de`, `en`, `es`, `it` | Limits recipes by available language. |
| `categories` | `pasta_and_rice`, `main_dishes_meat`, `main_dishes_fish`, `main_dishes_vegetarian`, and other schema values | Limits recipes to category names used by the MCP. |
| `tm_models` | `TM31`, `TM5`, `TM6`, `TM7` | Includes recipes compatible with any selected model. |
| `accessories` | `blade_cover`, `cutter`, `cooking_station`, `peeler`, `thermomix_sensor` | Includes recipes requiring any selected accessory. |
| `max_preparation_time` | `15`, `30`, `45` | Maximum preparation time in minutes. |
| `max_total_time` | `15`, `30`, `45` | Maximum total time in minutes. |
| `portions` | `1`, `2`, `4`, `6`, `8` | Exact portion count; `8` means eight or more. |
| `tags` | Cookidoo tag values | Filters recipe tags. |
| `dietary` | Cookidoo dietary values | Filters dietary labels. |
| `free_of_ingredients` | Values such as `gluten_free`, `lactose_free`, `nut_free` | Filters recipes free of selected ingredients. |
| `ingredient_categories` | Cookidoo ingredient-category values | Filters ingredient categories. |
| `nutrition_goals` | Cookidoo nutrition-goal values | Filters nutrition goals. |
| `cultural` | Cookidoo cultural/origin values | Filters cultural recipe origin. |
| `health_evaluation` | Cookidoo health-evaluation values | Filters health evaluations. |
| `recipe_characteristics` | Cookidoo recipe-characteristic values | Filters recipe characteristics. |

## Credits

Built on top of the [cookidoo-api](https://github.com/miaucl/cookidoo-api) package by miaucl.
