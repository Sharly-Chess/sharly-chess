"""The tie-break sets the plugins offer rank on the points before anything
else."""

from unittest import TestCase

import pytest

from data.tie_breaks.system_sets import SystemTieBreakSet
from data.tie_breaks.tie_breaks import PointsTieBreak
from plugins.ffe.ffe import FfePlugin
from plugins.fra_schools.fra_schools import FRASchoolsPlugin


@pytest.mark.unit
class PluginSwissTieBreakSetsTestCase(TestCase):
    def test_every_set_leads_on_points(self) -> None:
        system_sets: list[SystemTieBreakSet] = []
        FfePlugin().insert_swiss_system_tie_break_sets(system_sets=system_sets)
        FRASchoolsPlugin().insert_swiss_system_tie_break_sets(system_sets=system_sets)
        self.assertTrue(system_sets)
        for system_set in system_sets:
            with self.subTest(system_set.key):
                self.assertIsInstance(system_set.tie_breaks[0], PointsTieBreak)
