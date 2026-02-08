import time
from datetime import datetime, date
from unittest import TestCase

import pytest

from utils.date_time import (
    timestamp_to_datetime,
    datetime_to_timestamp,
    timestamp_to_date,
    date_to_timestamp,
)


@pytest.mark.unit
class TestTimestampToDatetime(TestCase):
    def test_valid_timestamp(self):
        ts = 1738953600.0
        result = timestamp_to_datetime(ts)
        assert isinstance(result, datetime)
        assert result == datetime.fromtimestamp(ts)

    def test_none(self):
        assert timestamp_to_datetime(None) is None

    def test_zero_epoch(self):
        result = timestamp_to_datetime(0.0)
        assert isinstance(result, datetime)
        assert result == datetime.fromtimestamp(0.0)

    def test_current_time(self):
        before = datetime.now()
        result = timestamp_to_datetime(time.time())
        after = datetime.now()
        assert before <= result <= after

    def test_negative_timestamp(self):
        result = timestamp_to_datetime(-86400.0)
        assert isinstance(result, datetime)
        assert result.year <= 1970


@pytest.mark.unit
class TestDatetimeToTimestamp(TestCase):
    def test_valid_datetime(self):
        dt = datetime(2025, 2, 7, 14, 0, 0)
        result = datetime_to_timestamp(dt)
        assert isinstance(result, float)
        assert result == dt.timestamp()

    def test_none(self):
        assert datetime_to_timestamp(None) is None


@pytest.mark.unit
class TestTimestampToDate(TestCase):
    def test_valid_timestamp(self):
        ts = 1738953600.0
        result = timestamp_to_date(ts)
        assert isinstance(result, date)
        assert not isinstance(result, datetime)
        assert result == datetime.fromtimestamp(ts).date()

    def test_none(self):
        assert timestamp_to_date(None) is None

    def test_strips_time(self):
        # Two timestamps on the same day should give the same date
        ts_morning = datetime(2025, 2, 7, 8, 0, 0).timestamp()
        ts_evening = datetime(2025, 2, 7, 20, 0, 0).timestamp()
        assert timestamp_to_date(ts_morning) == timestamp_to_date(ts_evening)


@pytest.mark.unit
class TestDateToTimestamp(TestCase):
    def test_valid_date(self):
        d = date(2025, 2, 7)
        result = date_to_timestamp(d)
        assert isinstance(result, float)
        assert result > 0

    def test_none(self):
        assert date_to_timestamp(None) is None

    def test_uses_midnight(self):
        d = date(2025, 2, 7)
        result = date_to_timestamp(d)
        dt = datetime.fromtimestamp(result)
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0
