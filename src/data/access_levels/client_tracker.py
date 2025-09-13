import time
from dataclasses import dataclass

from common.singleton import Singleton


@dataclass
class ClientRecord:
    host: str
    event_uniq_id: str | None
    username: str | None
    time: float


class ClientTracker(metaclass=Singleton):
    """The class that allows the memory-storage of the client connections."""

    client_records_by_host: dict[str, ClientRecord] = {}

    def track_client(
        self,
        host: str,
        event_uniq_id: str | None = None,
        username: str | None = None,
    ):
        """Adds a record if the host was not known or just updates the connection time."""
        self.client_records_by_host[host] = ClientRecord(
            host, event_uniq_id, username, time.time()
        )

    @property
    def client_records_sorted_by_host(self) -> list[ClientRecord]:
        """Returns the list of the client record sorted by host."""
        return sorted(
            self.client_records_by_host.values(),
            key=lambda client_record: client_record.host,
        )

    @property
    def client_records_sorted_by_date(self) -> list[ClientRecord]:
        """Returns the list of the client record sorted by time (last seen first)."""
        return sorted(
            self.client_records_by_host.values(),
            key=lambda client_record: -client_record.time,
        )
