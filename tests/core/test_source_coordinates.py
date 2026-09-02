from __future__ import annotations

import hashlib
import unittest

from packages.core.source_coordinates import (
    DeterministicFixtureProvider,
    ParserNeutralIndex,
    SourceCoordinate,
    source_snapshot,
)


class SourceCoordinateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = source_snapshot({"src/example.py": b"def greet(name):\n    return name\n"})

    def test_coordinate_round_trip_is_immutable_and_source_bound(self) -> None:
        source = self.snapshot.source("src/example.py")
        coordinate = SourceCoordinate(self.snapshot.snapshot_sha256, source.path, source.source_sha256, 0, 15, 1, 1, "function", "definition", "greet")
        self.assertEqual(coordinate, SourceCoordinate.from_dict(coordinate.to_dict()))
        self.assertEqual(hashlib.sha256(source.content).hexdigest(), coordinate.source_sha256)
        with self.assertRaises(AttributeError):
            coordinate.symbol = "other"  # type: ignore[misc]

    def test_fixture_provider_is_deterministic_and_queryable(self) -> None:
        source = self.snapshot.source("src/example.py")
        coordinate = SourceCoordinate(self.snapshot.snapshot_sha256, source.path, source.source_sha256, 0, 15, 1, 1, "function", "definition", "greet")
        first = DeterministicFixtureProvider((coordinate,)).index(self.snapshot)
        second = DeterministicFixtureProvider((coordinate,)).index(self.snapshot)
        self.assertEqual(first, second)
        self.assertEqual((coordinate,), ParserNeutralIndex(first).find("greet", role="definition"))

    def test_unsupported_provider_defers_without_coordinates(self) -> None:
        result = DeterministicFixtureProvider(supported=False).index(self.snapshot)
        self.assertFalse(result.supported)
        self.assertEqual((), result.coordinates)
        self.assertEqual("parser_unsupported", result.reason)

    def test_snapshot_or_source_mismatch_is_rejected(self) -> None:
        source = self.snapshot.source("src/example.py")
        coordinate = SourceCoordinate("f" * 64, source.path, source.source_sha256, 0, 1, 1, 1, "token", "reference", "def")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            DeterministicFixtureProvider((coordinate,)).index(self.snapshot)


if __name__ == "__main__":
    unittest.main()
