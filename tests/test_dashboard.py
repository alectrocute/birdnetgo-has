"""Regression checks for generated dashboard templates without HA installed."""

import ast
import unittest
from pathlib import Path
from typing import Any

from jinja2 import Environment


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
namespace = {**templates, "Any": Any, "DASHBOARD_TITLE": "Birds", "DASHBOARD_ICON": "mdi:bird"}
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

    def render(self, template, birds, available=True):
        environment = Environment()
        environment.filters["timestamp_custom"] = lambda *_: "09:15"
        environment.filters["as_timestamp"] = lambda value: value
        return environment.from_string(template).render(
            has_value=lambda _: available,
            state_attr=lambda *_: birds if available else None,
            today_at=lambda time: time,
            as_timestamp=lambda time: time,
            as_datetime=lambda time: time,
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
        self.assertIn("No notable arrivals", empty)
        unavailable = self.render(templates["MIGRATION_TEMPLATE"], [], False)
        self.assertIn("enhanced database", unavailable)

    def test_default_dashboard_uses_name_and_count_states(self):
        config = namespace["_default_config"](
            "sensor.daily", "sensor.summary", "sensor.interest",
            "http://birdnet.local", "sensor.latest", "sensor.detections",
            "camera.latest_image", "sensor.foy", "camera.foy_image",
            "sensor.history", "sensor.migration",
        )
        view = config["views"][0]
        self.assertEqual(view["max_columns"], 1)
        sections = view["sections"]
        self.assertEqual([section["column_span"] for section in sections], [1] * len(sections))
        hero = sections[0]["cards"][0]
        self.assertEqual(hero["type"], "picture-entity")
        self.assertEqual(hero["entity"], "sensor.latest")
        self.assertEqual(hero["camera_image"], "camera.latest_image")
        self.assertGreaterEqual(hero["grid_options"]["rows"], 5)
        foy_picture = sections[0]["cards"][-1]
        self.assertEqual(foy_picture["type"], "picture-entity")
        self.assertEqual(foy_picture["entity"], "sensor.foy")
        self.assertEqual(foy_picture["camera_image"], "camera.foy_image")
        titles = [section["title"] for section in sections]
        self.assertIn("Trends", titles)
        self.assertIn("First of year", titles)
        trend = sections[titles.index("Trends")]["cards"]
        self.assertEqual([card["entity"] for card in trend], [
            "sensor.history", "sensor.migration",
        ])
        foy_section = sections[titles.index("First of year")]["cards"]
        self.assertEqual(foy_section[0]["entity"], "sensor.foy")
        self.assertIn("__HISTORY__", templates["HISTORY_TEMPLATE"])
        self.assertIn("__MIGRATION__", templates["MIGRATION_TEMPLATE"])
        self.assertIn("__DAILY__", templates["FIRST_OF_YEAR_TEMPLATE"])
        tiles = [card for card in sections[0]["cards"] if card["type"] == "tile"]
        self.assertEqual([card["entity"] for card in tiles], [
            "sensor.daily", "sensor.detections", "sensor.latest", "sensor.interest",
        ])
        self.assertTrue(all(card["grid_options"]["columns"] == 3 for card in tiles))
        self.assertFalse(
            any(
                card["type"] == "statistics-graph"
                for section in sections
                for card in section["cards"]
            )
        )
        for section in sections[1:]:
            for card in section["cards"]:
                self.assertEqual(card["grid_options"]["columns"], 12)


if __name__ == "__main__":
    unittest.main()
