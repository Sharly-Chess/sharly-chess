# Playwright Testing Setup

This directory contains end-to-end tests using Playwright for Python. The tests automatically manage the backend server lifecycle to ensure your application is running before tests execute.

## Setup

### Prerequisites

Make sure you have the required dependencies installed:

```bash
# Install the package with test dependencies
pip install -e ".[tests]"

# Install Playwright browsers
playwright install
```

### Test Structure

- `conftest.py` - pytest configuration with Playwright fixtures and backend server management
- `test_config.py` - Configuration and utilities for testing
- `test_e2e_basic.py` - Basic end-to-end tests
- `screenshots/` - Directory for test screenshots (auto-created)
- `data/` - Test data files (if needed)

## Running Tests

### Basic Usage

```bash
# Run all tests
pytest

# Run with the test runner script
python run_tests.py

# Run specific test file
pytest tests/test_e2e_basic.py

# Run specific test
pytest tests/test_e2e_basic.py::TestBasicFunctionality::test_homepage_loads
```

### Test Categories

```bash
# Run only end-to-end tests
pytest -m e2e

# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"
```

### Development Options

```bash
# Run with visible browser (for debugging)
pytest --headed

# Run with coverage
pytest --cov=src --cov-report=html

# Run with detailed output
pytest -v --showlocals

# Run in parallel
pytest -n 4
```

### Using the Test Runner Script

The `run_tests.py` script provides convenient shortcuts:

```bash
# Basic test run
./run_tests.py

# Run only e2e tests
./run_tests.py --e2e-only

# Run with coverage and visible browser
./run_tests.py --coverage --headed

# Run specific test file with debug output
./run_tests.py tests/test_e2e_basic.py --debug --verbose

# Run fast tests only (skip slow ones)
./run_tests.py --fast
```

## Configuration

### Backend Server

**Important**: The backend server **only starts for e2e tests**. Unit tests run without any server startup, making them much faster.

The server automatically starts when:
- Running tests marked with `@pytest.mark.e2e`
- Using `pytest -m e2e` or `./run_tests.py --e2e-only`

The server configuration is in `test_config.py`. You may need to adjust:

- `TEST_HOST` and `TEST_PORT` for the server address
- `get_test_env_vars()` for environment variables your app needs
- Server startup command in `conftest.py`

### Test Environment

The test environment is isolated with:

- Separate environment variables
- Isolated server instance

## Writing Tests

### Basic Test Structure

```python
async def test_example(page: Page):
    \"\"\"Test example functionality.\"\"\"
    await page.goto(f"{page.base_url}/")
    await page.wait_for_load_state("networkidle")

    # Your test assertions here
    await expect(page.locator("h1")).to_contain_text("Expected Text")
```

### Using Test Utilities

```python
from tests.test_config import TestUtils

async def test_with_utilities(page: Page):
    # Take screenshot for debugging
    await TestUtils.take_screenshot(page, "test_step_1")
```

### Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.e2e
async def test_end_to_end_flow(page: Page):
    \"\"\"Full end-to-end test.\"\"\"
    pass

@pytest.mark.slow
async def test_large_dataset(page: Page):
    \"\"\"Test with large dataset.\"\"\"
    pass
```

## Debugging

### Taking Screenshots

Screenshots are automatically saved on test failures. You can also take manual screenshots:

```python
await TestUtils.take_screenshot(page, "debug_point")
```

### Running with Visible Browser

Use `--headed` flag to see the browser during test execution:

```bash
pytest --headed tests/test_e2e_basic.py
```

### Test Isolation

Each test gets:

- Fresh browser context
- Clean page instance

The backend server is shared across all tests in a session for performance.
