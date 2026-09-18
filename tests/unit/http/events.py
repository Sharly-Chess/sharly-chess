"""An event a test creates, drives over HTTP and reads back."""

from typing import Any

from data.event import Event
from data.loader import EventLoader
from data.tournament import Tournament
from tests.test_config import TestUtils


class EventUnderTest:
    """A request of its own writes to the database, and the copy a test
    loaded does not see that, so every read is a fresh load. An Event is
    held weakly by what it owns, so the loaded copies are kept for as
    long as the test runs."""

    def __init__(self, event_id: str, tournament_name: str | None = None) -> None:
        self.id = event_id
        self.tournament_name = tournament_name
        self._loaded: list[Event] = []

    def create(
        self,
        *,
        event: dict[str, Any] | None = None,
        tournament: dict[str, Any] | None = None,
        json_file: str | None = None,
    ) -> None:
        TestUtils.create_event(self.id, overrides=event)
        if self.tournament_name is not None:
            TestUtils.create_tournament(
                self.id,
                self.tournament_name,
                json_file=json_file,
                overrides=tournament,
            )

    def load(self) -> Event:
        EventLoader.unload_event(self.id)
        loaded = EventLoader().load_event(self.id)
        self._loaded.append(loaded)
        return loaded

    def tournament(self) -> Tournament:
        assert self.tournament_name is not None
        return self.load().tournaments_by_name[self.tournament_name]

    def delete(self) -> None:
        self._loaded.clear()
        EventLoader.unload_event(self.id)
        TestUtils.delete_event(self.id)
