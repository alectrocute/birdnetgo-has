"""Regression checks for generated dashboard templates without HA installed."""

import ast
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined


SOURCE = Path(__file__).resolve().parents[1] / "custom_components/birdnetgo/dashboard.py"
module = ast.parse(SOURCE.read_text())
templates = {
    target.id: ast.literal_eval(node.value)
    for node in module.body
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name) and target.id.endswith("_TEMPLATE")
}
functions = ast.Module(
    body=[
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("_render", "_tile", "_default_config")
    ],
    type_ignores=[],
)
namespace = {
    **templates,
    "Any": Any,
    "DASHBOARD_TITLE": "Birds",
    "DASHBOARD_ICON": "mdi:bird",
    "FIRST_OF_YEAR_EMPTY_STATE": "None today",
}
exec(compile(functions, str(SOURCE), "exec"), namespace)


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
        for name in ("DAILY_TEMPLATE", "LATEST_TEMPLATE", "BRAND_NEW_TEMPLATE", "INTEREST_TEMPLATE"):
            with self.subTest(template=name):
                output = self.render(templates[name], self.birds)
                lines = output.splitlines()
                separator = next(i for i, line in enumerate(lines) if line.startswith("| :--"))
                self.assertTrue(any("Blue Jay" in line for line in lines[separator + 1 : separator + 3]))
                self.assertTrue(any("Robin" in line for line in lines[separator + 1 : separator + 3]))
                self.assertNotIn("\n\n", "\n".join(lines[separator : separator + 3]))
                if name == "DAILY_TEMPLATE":
                    self.assertIn("\n\n**5 detections**", output)

    def test_empty_and_offline(self):
        for name, template in templates.items():
            if name in ("OVERVIEW_TEMPLATE", "MIGRATION_TEMPLATE"):
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
        self.assertIn("- Bird 0", output)
        self.assertIn("- Bird 2", output)
        self.assertNotIn("Bird 3", output)
        self.assertIn("_+5 more arrivals_\n\n**Gone quiet · 5**", output)
        self.assertIn("- Quiet 1 · 11 days", output)
        self.assertNotIn("Quiet 2", output)
        self.assertIn("_+3 more_", output)

    def test_history_is_a_compact_summary(self):
        output = self.render(
            templates["HISTORY_TEMPLATE"],
            [],
            attributes={
                "daily_counts": {"2026-09-22": 5, "2026-09-23": 7},
                "sparkline": "▃▄█",
            },
        )
        self.assertIn("**12 detections** in 2 days · best day **7**", output)
        self.assertNotIn("▃▄█", output)

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

    def test_default_dashboard_uses_name_and_count_states(self):
        config = namespace["_default_config"](
            "sensor.daily", "sensor.summary", "sensor.interest",
            "http://birdnet.local", "sensor.latest", "sensor.detections",
            "sensor.lifetime", "camera.latest_image", "sensor.foy",
            "sensor.history", "sensor.migration",
        )
        view = config["views"][0]
        self.assertEqual(view["max_columns"], 2)
        sections = view["sections"]
        self.assertEqual(
            [section["column_span"] for section in sections],
            [2, 1, 1, 2, 1, 1, 2],
        )
        hero = sections[0]["cards"][0]
        self.assertEqual(hero["type"], "picture-entity")
        self.assertEqual(hero["entity"], "sensor.latest")
        self.assertEqual(hero["camera_image"], "camera.latest_image")
        self.assertEqual(hero["grid_options"], {"columns": 6, "rows": 3})
        self.assertEqual(
            sum(card["type"] == "picture-entity" for card in sections[0]["cards"]), 1
        )
        titles = [section["title"] for section in sections]
        self.assertIn("Trends", titles)
        self.assertIn("First of year", titles)
        trend = sections[titles.index("Trends")]["cards"]
        self.assertEqual([card["entity"] for card in trend], [
            "sensor.history", "sensor.migration",
            "sensor.history", "sensor.migration",
        ])
        self.assertEqual([card["type"] for card in trend], [
            "tile", "tile", "markdown", "markdown",
        ])
        foy_section = sections[titles.index("First of year")]["cards"]
        self.assertEqual(foy_section[0]["type"], "tile")
        self.assertEqual(foy_section[0]["entity"], "sensor.foy")
        self.assertEqual(foy_section[1]["type"], "conditional")
        self.assertEqual(foy_section[1]["conditions"][0]["entity"], "sensor.foy")
        self.assertIn("None today", foy_section[1]["conditions"][0]["state_not"])
        self.assertEqual(foy_section[1]["card"]["entity"], "sensor.daily")
        self.assertIn("__HISTORY__", templates["HISTORY_TEMPLATE"])
        self.assertIn("__MIGRATION__", templates["MIGRATION_TEMPLATE"])
        self.assertIn("__DAILY__", templates["FIRST_OF_YEAR_TEMPLATE"])
        tiles = [card for card in sections[0]["cards"] if card["type"] == "tile"]
        self.assertEqual([card["entity"] for card in tiles], [
            "sensor.daily", "sensor.detections", "sensor.lifetime",
            "sensor.latest", "sensor.interest",
        ])
        self.assertTrue(all(card["grid_options"]["columns"] == 3 for card in tiles))
        open_button = sections[0]["cards"][-1]
        self.assertEqual(open_button["type"], "button")
        self.assertEqual(open_button["tap_action"], {
            "action": "url", "url_path": "http://birdnet.local",
        })
        self.assertFalse(
            any(
                card["type"] == "statistics-graph"
                for section in sections
                for card in section["cards"]
            )
        )
        for section in sections[3:]:
            for card in section["cards"]:
                self.assertEqual(card["grid_options"]["columns"], 12)


if __name__ == "__main__":
    unittest.main()
