# _Sharly Chess_ - Contributing guide

Thank you for investing your time in our project.

## New contributor guide

To get an overview of the project, read the [user documentation](https://sharly-chess.com).

Please note that this project is licenced under the [GNU Affero Public Licence version 3.0](https://sharly-chess.com/license).

## Start contributing

### Issues

If you spot a problem in the program or want to request a feature, [search if an issue already exists](https://github.com/sharly-chess/sharly-chess/issues).

If a related issue doesn't exist, you can open a new issue using a relevant [issue form](https://github.com//sharly-chess/sharly-chess/issues/new/choose).

### Contributing code

This project uses [Python 3.12](https://www.python.org/downloads/release/python-3129/), and is reliant on Windows-specific APIs.
As such, this project does not support Linux or MacOS, or any other operating system.
This will change in the future.

If you want to contribute code, please [create a fork of our repository](https://github.com/sharly-chess/sharly-chess/fork), and clone it locally.

To install the relevant packages for development, run: `pip install -e .[lint,tests]`

There are two other optional dependency groups: `translate` (for translating to locales other than French and English), and `export` (for exporting to a release format).

Before contributing code, please install our pre-commit hooks by running `pre-commit install`

Create a branch with a descriptive name, and start coding the changes.
Make sure you only add one feature or solve one issue, otherwise your Pull Request will not pass code review.

Whenever possible, please add tests to ensure your changes do not cause regressions in the code.

Make sure to run `pytest` and solve problems before sending your code to review.

Once all the changes are made, create a Pull Request with a descriptive name, and why you made the changes.
If you're solving an issue, link to it in when opening your PR.

### Code review

Once you have opened your PR, we will try to start reviewing it as soon as possible.

If your code changes are acceptable, we will merge your code, otherwise, there might be several revision rounds before merging or refusing your PR.
