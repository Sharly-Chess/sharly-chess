# Tests

The suite has three tiers:

- `unit/` — pure Python: pairing engines, scoring, tie-breaks, exports, the
  database layer. No server, no browser.
- `unit/http/` — the application driven over HTTP in this process. Litestar's
  test client calls the same handlers the server does, so a form is refused,
  a modal renders or a record lands in the database in a millisecond, without
  a browser or a socket. Anything a browser test does not need the browser
  for belongs here.
- `e2e/` — Playwright against a real server, for what only a browser can
  show: htmx swaps, keyboard entry, screens rotating.
- `gacrux/` — the TRF26 export of every test tournament, checked by Gacrux,
  an independent pairing and tie-break checker (fetched into `tools/` on first
  run). Left out of both CI suites and run by hand for the
  endorsement. See `docs/technical-appendices/fide-endorsement.md`.

## Setup

```bash
pip install -e ".[tests]"
playwright install chromium
```

## Running

```bash
# Everything but the release-only tests
TEST_ENV=true ./venv/bin/pytest

# One tier
TEST_ENV=true ./venv/bin/pytest tests/unit
TEST_ENV=true ./venv/bin/pytest tests/unit/http
TEST_ENV=true ./venv/bin/pytest tests/e2e

# By marker
pytest -m unit
pytest -m e2e

# The Gacrux checks, which no default run includes (see above)
TEST_ENV=true pytest tests/gacrux -m gacrux

# Release-only tests are skipped by default; a release runs them with
pytest -m "not gacrux"

# With coverage (the floor is in pyproject.toml, under [tool.coverage.report])
pytest --cov --cov-report=term-missing:skip-covered

# Serially (the default is four pytest-xdist workers)
pytest -n 0
```

The backend server only starts when an `e2e`-marked test is selected; the
other tiers run without it.

## Layout

- `conftest.py` (repository root) — markers, the backend server, Playwright
  fixtures.
- `test_config.py` — `TestUtils`, which creates events, tournaments and
  screens for a test, over HTTP or straight into the database.
- `unit/http/conftest.py` — the in-process application and its clients:
  `http` (from localhost, so an administrator), `lan` (a visitor on the
  venue's network) and `api` (the request context `TestUtils` builds through).
- `unit/http/events.py` — `EventUnderTest`, an event a test creates, drives
  and reads back from the database after each request.
- `screenshots/` — where `TestUtils.take_screenshot` writes.

## Writing an HTTP test

```python
from tests.unit.http.events import EventUnderTest

EVENT_ID = 'test-timers-http'
EVENT = EventUnderTest(EVENT_ID)


@pytest.fixture
def event() -> Iterator[str]:
    EVENT.create()
    yield EVENT_ID
    EVENT.delete()


@pytest.mark.unit
def test_a_timer_is_created(http: TestClient, event: str):
    response = http.post(f'/timer-create/{EVENT_ID}', data={'name': 'Round one'})
    assert response.status_code == 200
    assert [timer.name for timer in EVENT.load().timers_by_id.values()] == ['Round one']
```

A request of its own writes to the database, and the copy a test loaded does
not see that: read the event back with `EVENT.load()` (or
`EVENT.tournament()`) after every request whose effect is asserted.

## Writing a browser test

```python
@pytest.mark.e2e
async def test_example(page: Page):
    await page.goto('/')
    await expect(page.locator('h1')).to_contain_text('Sharly Chess')
```

Run with `--headed` to watch the browser, and
`TestUtils.take_screenshot(page, 'step')` to keep a frame of it.
