"""Regression checks for the bundled dashboard layouts, without HA installed."""

import ast
import asyncio
import unittest
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

SOURCE = (
    Path(__file__).resolve().parents[1] / "custom_components/birdnetgo/dashboard.py"
)
DASHBOARDS_DIR = SOURCE.parent / "dashboards"

module = ast.parse(SOURCE.read_text())
functions = ast.Module(
    body=[
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        ),
        *(
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name
            in ("_render", "_load_layout", "_lovelace_data", "_has_button_card")
        ),
    ],
    type_ignores=[],
)
namespace: dict[str, Any] = {
    "Any": Any,
    "Path": Path,
    "suppress": suppress,
    "yaml": yaml,
    "DASHBOARDS_DIR": DASHBOARDS_DIR,
}
ast.fix_missing_locations(functions)
exec(  # noqa: S102
    compile(functions, str(SOURCE), "exec"),
    namespace,
)

ENTITIES = {
    "__DAILY__": "sensor.daily",
    "__SPECIES__": "sensor.summary",
    "__INTEREST__": "sensor.interest",
    "__LATEST_BIRD__": "sensor.latest",
    "__DETECTIONS__": "sensor.detections",
    "__LIFETIME__": "sensor.lifetime",
    "__CAMERA__": "camera.latest_image",
    "__FOY__": "sensor.foy",
    "__HISTORY__": "sensor.history",
    "__MIGRATION__": "sensor.migration",
    "__FIRST_BIRD__": "sensor.first_bird",
    "__BASE_URL__": "http://birdnet.local",
}

render_layout = namespace["_render"]
DEFAULT_CONFIG = render_layout(namespace["_load_layout"]("default"), ENTITIES)
BUTTON_CONFIG = render_layout(namespace["_load_layout"]("button-card"), ENTITIES)


def _templates_by_section(config: dict[str, Any]) -> dict[str, list[str]]:
    """Return the markdown/Jinja contents of each titled section."""
    result: dict[str, list[str]] = {}
    for section in config["views"][0]["sections"]:
        contents = [
            card["card"]["content"]
            if card["type"] == "conditional"
            else card["content"]
            for card in section["cards"]
            if card["type"] in ("markdown", "conditional")
        ]
        if contents:
            result[section["title"]] = contents
    return result


_templates = _templates_by_section(DEFAULT_CONFIG)
DAILY_TEMPLATE = _templates["Today's visitors"][0]
LATEST_TEMPLATE = _templates["Latest detections"][0]
BRAND_NEW_TEMPLATE = _templates["New species"][0]
INTEREST_TEMPLATE = _templates["Birds of interest"][0]
HISTORY_TEMPLATE, MIGRATION_TEMPLATE, FIRST_OF_YEAR_TEMPLATE = _templates["Trends"]
templates = {
    "DAILY_TEMPLATE": DAILY_TEMPLATE,
    "LATEST_TEMPLATE": LATEST_TEMPLATE,
    "BRAND_NEW_TEMPLATE": BRAND_NEW_TEMPLATE,
    "INTEREST_TEMPLATE": INTEREST_TEMPLATE,
    "HISTORY_TEMPLATE": HISTORY_TEMPLATE,
    "MIGRATION_TEMPLATE": MIGRATION_TEMPLATE,
    "FIRST_OF_YEAR_TEMPLATE": FIRST_OF_YEAR_TEMPLATE,
}


def _strings(value: Any) -> Any:
    """Yield every string in a nested config structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.birds = [
            {
                "common_name": "Blue Jay",
                "species_code": "blujay",
                "count": 3,
                "latest_heard": "09:15:00",
                "last_heard": "2026-09-23 09:15:00",
                "first_heard": "2026-09-20 09:15:00",
                "hourly_counts": [1] * 24,
            },
            {
                "common_name": "Robin",
                "species_code": "amerob",
                "count": 2,
                "latest_heard": "08:10:00",
                "last_heard": "2026-09-23 08:10:00",
                "first_heard": "2026-09-21 08:10:00",
                "hourly_counts": [0] * 24,
            },
        ]

    def render(self, template, birds, available=True, attributes=None):
        environment = Environment(undefined=StrictUndefined)
        environment.filters["timestamp_custom"] = lambda *_: "09:15"
        environment.filters["as_timestamp"] = lambda value: value
        attrs = {"species_list": birds, **(attributes or {})}
        return environment.from_string(template).render(
            has_value=lambda _: available,
            state_attr=lambda _, attr: attrs.get(attr) if available else None,
            today_at=lambda time: time,
            as_timestamp=lambda time: time,
            as_datetime=datetime.fromisoformat,
            relative_time=lambda _: "just now",
        )

    def test_tables_have_adjacent_rows(self):
        for name in (
            "DAILY_TEMPLATE",
            "LATEST_TEMPLATE",
            "BRAND_NEW_TEMPLATE",
            "INTEREST_TEMPLATE",
        ):
            with self.subTest(template=name):
                output = self.render(templates[name], self.birds)
                lines = output.splitlines()
                separator = next(
                    i for i, line in enumerate(lines) if line.startswith("| :--")
                )
                self.assertTrue(
                    any(
                        "Blue Jay" in line
                        for line in lines[separator + 1 : separator + 3]
                    )
                )
                self.assertTrue(
                    any(
                        "Robin" in line for line in lines[separator + 1 : separator + 3]
                    )
                )
                self.assertNotIn("\n\n", "\n".join(lines[separator : separator + 3]))
                if name == "DAILY_TEMPLATE":
                    self.assertIn("\n\n**5 detections**", output)

    def test_empty_and_offline(self):
        for name, template in templates.items():
            if name == "MIGRATION_TEMPLATE":
                continue
            self.assertNotIn("| :--", self.render(template, []))
            self.assertIn("Waiting for BirdNET-Go", self.render(template, [], False))

    def test_migration_template_states(self):
        empty = self.render(templates["MIGRATION_TEMPLATE"], [])
        self.assertIn("enhanced database", empty)
        nothing = self.render(
            templates["MIGRATION_TEMPLATE"],
            [],
            attributes={"new_arrivals": [], "gone_quiet": []},
        )
        self.assertIn("No notable arrivals", nothing)
        one_sided = self.render(
            templates["MIGRATION_TEMPLATE"],
            [],
            attributes={
                "new_arrivals": [],
                "gone_quiet": [{"common_name": "Oriole", "days_since": 18}],
            },
        )
        self.assertIn("**New arrivals · 0**", one_sided)
        self.assertIn("**Gone quiet · 1**", one_sided)
        unavailable = self.render(templates["MIGRATION_TEMPLATE"], [], False)
        self.assertIn("enhanced database", unavailable)

    def test_migration_card_limits_large_lists(self):
        arrivals = [f"Bird {i}" for i in range(8)]
        quiet = [{"common_name": f"Quiet {i}", "days_since": i + 10} for i in range(5)]
        output = self.render(
            templates["MIGRATION_TEMPLATE"],
            [],
            attributes={"new_arrivals": arrivals, "gone_quiet": quiet},
        )
        self.assertIn("**New arrivals · 8**", output)
        self.assertIn("- Bird 0", output)
        self.assertIn("- Bird 2", output)
        self.assertNotIn("Bird 3", output)
        self.assertIn("_+5 more_\n\n**Gone quiet · 5**", output)
        self.assertIn("- Quiet 2 · 12 days", output)
        self.assertNotIn("Quiet 3", output)
        self.assertIn("_+2 more_", output)
        self.assertNotIn("more arrivals", output)

    def test_history_is_a_compact_summary(self):
        output = self.render(
            templates["HISTORY_TEMPLATE"],
            [],
            attributes={
                "daily_counts": {"2026-09-22": 5, "2026-09-23": 7},
                "sparkline": "▃▄█",
            },
        )
        self.assertIn("▃▄█", output)
        self.assertIn("**12 detections** in 2 days · best day **7**", output)
        non_empty = [line for line in output.splitlines() if line.strip()]
        self.assertEqual(len(non_empty), 2)

    def test_first_of_year_handles_missing_flags_and_empty_states(self):
        template = templates["FIRST_OF_YEAR_TEMPLATE"]
        self.assertIn("No birds heard", self.render(template, []))
        self.assertIn(
            "No first-of-year sightings today", self.render(template, self.birds)
        )
        flagged = {
            **self.birds[1],
            "first_heard": "08:10:00",
            "is_new_this_year": True,
        }
        output = self.render(template, [self.birds[0], flagged])
        self.assertIn("- [Robin](https://ebird.org/species/amerob) · 09:15", output)
        self.assertNotIn("Blue Jay", output)
        not_new = {**self.birds[0], "is_new_this_year": False}
        self.assertIn(
            "No first-of-year sightings today", self.render(template, [not_new])
        )

    def test_default_layout_structure(self):
        view = DEFAULT_CONFIG["views"][0]
        self.assertEqual(view["max_columns"], 3)
        sections = view["sections"]
        self.assertEqual(
            [section["column_span"] for section in sections],
            [3, 3, 1, 1, 1, 3],
        )
        self.assertEqual(
            [section["title"] for section in sections],
            [
                "At a glance",
                "Trends",
                "Today's visitors",
                "Latest detections",
                "New species",
                "Birds of interest",
            ],
        )
        hero = sections[0]["cards"][0]
        self.assertEqual(hero["type"], "picture-entity")
        self.assertEqual(hero["entity"], "sensor.latest")
        self.assertEqual(hero["camera_image"], "camera.latest_image")
        self.assertEqual(hero["grid_options"], {"columns": 6, "rows": 3})
        self.assertEqual(
            sum(card["type"] == "picture-entity" for card in sections[0]["cards"]), 1
        )
        trend = sections[1]["cards"]
        self.assertEqual(
            [card["entity"] for card in trend if card["type"] != "conditional"],
            [
                "sensor.history",
                "sensor.migration",
                "sensor.foy",
                "sensor.history",
                "sensor.migration",
            ],
        )
        self.assertEqual(
            [card["type"] for card in trend],
            [
                "tile",
                "tile",
                "tile",
                "markdown",
                "markdown",
                "conditional",
            ],
        )
        self.assertTrue(all(card["grid_options"]["columns"] == 4 for card in trend[:3]))
        self.assertEqual(
            [card["grid_options"]["columns"] for card in trend[3:]], [6, 6, 6]
        )
        foy_tile = trend[2]
        self.assertEqual(foy_tile["name"], "First of year")
        self.assertEqual(foy_tile["icon"], "mdi:calendar-star")
        foy_card = trend[5]
        self.assertEqual(foy_card["conditions"][0]["entity"], "sensor.foy")
        self.assertIn("None today", foy_card["conditions"][0]["state_not"])
        self.assertEqual(foy_card["card"]["entity"], "sensor.daily")
        tiles = [card for card in sections[0]["cards"] if card["type"] == "tile"]
        self.assertEqual(
            [card["entity"] for card in tiles],
            [
                "sensor.daily",
                "sensor.detections",
                "sensor.lifetime",
                "sensor.latest",
                "sensor.interest",
            ],
        )
        self.assertTrue(all(card["grid_options"]["columns"] == 3 for card in tiles))
        glance_icons = [card["icon"] for card in tiles]
        self.assertEqual(len(glance_icons), len(set(glance_icons)))
        open_button = sections[0]["cards"][-1]
        self.assertEqual(open_button["type"], "button")
        self.assertEqual(
            open_button["tap_action"],
            {
                "action": "url",
                "url_path": "http://birdnet.local",
            },
        )
        self.assertFalse(
            any(
                card["type"] == "statistics-graph"
                for section in sections
                for card in section["cards"]
            )
        )
        for section in sections[2:5]:
            for card in section["cards"]:
                self.assertEqual(card["grid_options"]["columns"], 12)
        interest_card = sections[5]["cards"][0]
        self.assertEqual(interest_card["grid_options"]["columns"], 6)

    def test_button_card_layout_structure(self):
        view = BUTTON_CONFIG["views"][0]
        self.assertEqual(view["path"], "birds")
        self.assertEqual(
            [badge["entity"] for badge in view["badges"]],
            ["sensor.lifetime", "sensor.interest", "sensor.summary"],
        )
        sections = view["sections"]
        self.assertEqual(len(sections), 2)
        self.assertTrue(all(section["column_span"] == 3 for section in sections))
        cards = sections[0]["cards"]
        self.assertEqual(
            [card["type"] for card in cards],
            [
                "picture-entity",
                "entity",
                "entity",
                "entity",
                "entity",
                "button",
                "history-graph",
            ],
        )
        hero = cards[0]
        self.assertEqual(hero["entity"], "sensor.latest")
        self.assertEqual(hero["camera_image"], "camera.latest_image")
        self.assertEqual(hero["grid_options"], {"columns": 9, "rows": 4})
        self.assertEqual(cards[1]["entity"], "sensor.first_bird")
        button = cards[5]
        self.assertEqual(
            button["tap_action"],
            {"action": "url", "url_path": "http://birdnet.local"},
        )
        history = cards[6]
        self.assertEqual(
            history["entities"], [{"entity": "sensor.latest", "name": "Detections"}]
        )
        table = sections[1]["cards"][0]
        self.assertEqual(table["type"], "custom:button-card")
        self.assertEqual(table["entity"], "sensor.daily")
        self.assertEqual(table["triggers_update"], ["sensor.daily"])
        content = table["custom_fields"]["content"]
        self.assertIn("[[[", content)
        self.assertIn("]]]", content)
        self.assertIn("species_list", content)
        self.assertIn("hourly_counts", content)
        self.assertIn("/api/v2/media/image/", content)
        self.assertIn("ebird.org", content)

    def test_rendered_layouts_have_no_leftover_placeholders(self):
        for name, config in (
            ("default", DEFAULT_CONFIG),
            ("button-card", BUTTON_CONFIG),
        ):
            with self.subTest(layout=name):
                self.assertEqual(config["version"], 1)
                self.assertEqual(len(config["views"]), 1)
                for text in _strings(config):
                    self.assertNotIn("__", text)

    def test_button_card_detection(self):
        has_button_card = namespace["_has_button_card"]

        class FakeResources:
            def __init__(self, items, fail=False):
                self._items = items
                self._fail = fail

            async def async_load(self):
                if self._fail:
                    raise RuntimeError("boom")

            def async_items(self):
                return self._items

        def hass_with(resources):
            return SimpleNamespace(
                data={"lovelace": SimpleNamespace(resources=resources)},
                config=SimpleNamespace(
                    path=lambda *parts: "/nonexistent/www/button-card.js"
                ),
            )

        self.assertTrue(
            asyncio.run(
                has_button_card(
                    hass_with(
                        FakeResources(
                            [{"url": "https://example.com/button-card.js?v=1"}]
                        )
                    )
                )
            )
        )
        self.assertFalse(
            asyncio.run(
                has_button_card(
                    hass_with(FakeResources([{"url": "…/mini-graph-card.js"}]))
                )
            )
        )
        self.assertFalse(asyncio.run(has_button_card(hass_with(FakeResources([])))))
        self.assertFalse(
            asyncio.run(has_button_card(hass_with(FakeResources([], fail=True))))
        )
        self.assertFalse(
            asyncio.run(
                has_button_card(SimpleNamespace(data={}, config=hass_with(None).config))
            )
        )


if __name__ == "__main__":
    unittest.main()
