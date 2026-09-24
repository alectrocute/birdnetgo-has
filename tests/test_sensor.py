"""Check first-of-year state against BirdNET-Go's daily response shape."""

import ast
import unittest
from pathlib import Path
from typing import Any


SOURCE = Path(__file__).resolve().parents[1] / "custom_components/birdnetgo/sensor.py"
module = ast.parse(SOURCE.read_text())
sensor_class = next(
    node
    for node in module.body
    if isinstance(node, ast.ClassDef) and node.name == "BirdNETGoFirstOfYearSensor"
)
namespace = {
    "Any": Any,
    "BirdNETGoEntity": object,
    "FIRST_OF_YEAR_EMPTY_STATE": "None today",
}
exec(compile(ast.Module(body=[sensor_class], type_ignores=[]), str(SOURCE), "exec"), namespace)


class FirstOfYearSensorTests(unittest.TestCase):
    def sensor(self, birds):
        instance = namespace["BirdNETGoFirstOfYearSensor"]()
        instance._species_list = lambda key: birds
        return instance

    def test_latest_daily_sighting_is_used_without_last_heard(self):
        birds = [
            {"common_name": "Blue Jay", "latest_heard": "09:15:00"},
            {
                "common_name": "Robin",
                "latest_heard": "08:10:00",
                "is_new_this_year": True,
            },
            {
                "common_name": "Hawk",
                "latest_heard": "17:30:00",
                "first_heard": "17:00:00",
                "species_code": "coohaw",
                "is_new_this_year": True,
            },
        ]
        sensor = self.sensor(birds)
        self.assertEqual(sensor.native_value, "Hawk")
        self.assertEqual(sensor.extra_state_attributes, {
            "first_heard": "17:00:00",
            "species_code": "coohaw",
        })

    def test_empty_state_when_nothing_is_new_this_year(self):
        sensor = self.sensor([{"common_name": "Blue Jay", "latest_heard": "09:15:00"}])
        self.assertEqual(sensor.native_value, "None today")
        self.assertEqual(sensor.extra_state_attributes, {})


if __name__ == "__main__":
    unittest.main()
