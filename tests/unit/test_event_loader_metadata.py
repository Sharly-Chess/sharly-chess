from data.event_metadata import EventMetadata
from data.loader import EventLoader


def test_newly_validated_metadata_is_reused(monkeypatch):
    metadata = EventMetadata(
        uniq_id='event',
        name='Event',
        federation='FRA',
        player_rating_type=1,
    )
    monkeypatch.setattr(EventLoader, '_valid_event_ids', set())
    monkeypatch.setattr(EventLoader, '_invalid_uniq_ids', set())
    monkeypatch.setattr(
        EventLoader, 'all_event_ids', classmethod(lambda cls: ['event'])
    )
    monkeypatch.setattr(
        EventLoader,
        '_clean_not_existing_event_database_files',
        classmethod(lambda cls, event_ids: None),
    )
    monkeypatch.setattr(
        EventLoader,
        'check_event_database',
        classmethod(lambda cls, event_id: metadata),
    )

    def fail_on_second_load(cls, event_id):
        raise AssertionError('metadata should come from validation')

    monkeypatch.setattr(
        EventLoader, 'load_event_metadata', classmethod(fail_on_second_load)
    )

    assert EventLoader.get_events_metadata() == [metadata]
