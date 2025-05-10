from abc import ABC
from unittest import TestCase

from common.sharly_chess_config import SharlyChessConfig
from data.event import Event
from data.loader import EventLoader
from database.sqlite.event.event_database import EventDatabase


def reload_test_database() -> Event:
    database = EventDatabase(SharlyChessConfig.test_event_uniq_id)
    database.file.unlink(missing_ok=True)
    database.create(populate=True)
    return EventLoader().load_event(SharlyChessConfig.test_event_uniq_id)


class BaseTestCase(TestCase, ABC):
    event = reload_test_database()
