"""Check first-of-year state against BirdNET-Go's daily response shape."""

import ast
import datetime as dt
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/birdnetgo/sensor.py"
module = ast.parse(SOURCE.read_text())
sensor_classes = [
    node
    for node in module.body
    if isinstance(node, ast.ClassDef)
    and node.name
    in (
        "BirdNETGoFirstOfYearSensor",
        "BirdNETGoFirstBirdTodaySensor",
        "BirdNETGoDailySummarySensor",
        "BirdNETGoSpeciesSummarySensor",
        "BirdNETGoBirdsOfInterestSensor",
        "BirdNETGoMigrationSensor",
    )
]


def _parse_datetime(raw: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _parse_time(raw: str) -> dt.time | None:
    try:
        return dt.time.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


class _StubDtUtil:
    DEFAULT_TIME_ZONE = dt.timezone.utc

    @staticmethod
    def parse_datetime(raw: str) -> dt.datetime | None:
        return _parse_datetime(raw)

    @staticmethod
    def parse_time(raw: str) -> dt.time | None:
        return _parse_time(raw)

    @staticmethod
    def start_of_local_day() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    @staticmethod
    def as_local(value: dt.datetime) -> dt.datetime:
        return value


namespace = {
    "Any": Any,
    "ATTR_SPECIES_LIST": "species_list",
    "BirdNETGoEntity": object,
    "FIRST_OF_YEAR_EMPTY_STATE": "None today",
    "dt_util": _StubDtUtil,
    "datetime": dt.datetime,
    "SensorDeviceClass": SimpleNamespace(TIMESTAMP="timestamp"),
    "SensorStateClass": SimpleNamespace(
        MEASUREMENT="measurement", TOTAL_INCREASING="total_increasing"
    ),
}
exec(  # noqa: S102
    compile(ast.Module(body=sensor_classes, type_ignores=[]), str(SOURCE), "exec"),
    namespace,
)


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
        self.assertEqual(
            sensor.extra_state_attributes,
            {
                "first_heard": "17:00:00",
                "species_code": "coohaw",
            },
        )

    def test_empty_state_when_nothing_is_new_this_year(self):
        sensor = self.sensor([{"common_name": "Blue Jay", "latest_heard": "09:15:00"}])
        self.assertEqual(sensor.native_value, "None today")
        self.assertEqual(sensor.extra_state_attributes, {})


class FirstBirdTodaySensorTests(unittest.TestCase):
    def sensor(self, birds):
        instance = namespace["BirdNETGoFirstBirdTodaySensor"]()
        instance._species_list = lambda key: birds
        return instance

    def test_clock_time_first_heard_is_parsed(self):
        birds = [
            {
                "common_name": "Blue Jay",
                "first_heard": "06:15:00",
                "species_code": "blujay",
            },
            {
                "common_name": "Robin",
                "first_heard": "04:35:00",
                "species_code": "amerob",
            },
        ]
        sensor = self.sensor(birds)
        self.assertEqual(sensor.native_value, "Robin")
        self.assertEqual(
            sensor.extra_state_attributes,
            {
                "first_heard": "04:35:00",
                "species_code": "amerob",
            },
        )

    def test_full_timestamps_are_still_supported(self):
        birds = [
            {"common_name": "Blue Jay", "first_heard": "2026-09-23 07:00:00"},
            {"common_name": "Robin", "first_heard": "2026-09-23 05:30:00"},
        ]
        self.assertEqual(self.sensor(birds).native_value, "Robin")

    def test_unknown_when_first_heard_is_missing_or_invalid(self):
        self.assertIsNone(self.sensor([]).native_value)
        self.assertIsNone(self.sensor([{"common_name": "Blue Jay"}]).native_value)
        self.assertIsNone(
            self.sensor(
                [{"common_name": "Blue Jay", "first_heard": "garbage"}]
            ).native_value
        )


class RecorderExclusionTests(unittest.TestCase):
    def test_bulky_list_attributes_are_unrecorded(self):
        for name in (
            "BirdNETGoDailySummarySensor",
            "BirdNETGoSpeciesSummarySensor",
            "BirdNETGoBirdsOfInterestSensor",
        ):
            self.assertEqual(
                namespace[name]._unrecorded_attributes,
                {"species_list"},
                name,
            )
        self.assertEqual(
            namespace["BirdNETGoMigrationSensor"]._unrecorded_attributes,
            {"new_arrivals", "gone_quiet"},
        )


if __name__ == "__main__":
    unittest.main()
