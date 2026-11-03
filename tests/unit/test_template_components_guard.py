"""The admin templates hold no more hand-written component markup than the
baseline allows, and the check counts that markup correctly."""

import pytest

from scripts.lint.template_components import (
    compare,
    count_text,
    current_counts,
    load_baseline,
)


@pytest.mark.unit
def test_templates_stay_within_the_baseline() -> None:
    increases, decreases = compare(current_counts(), load_baseline())
    assert not increases, 'Hand-written component markup has grown:\n' + '\n'.join(
        increases
    )
    assert not decreases, (
        'Hand-written component markup has shrunk; run '
        '`python scripts/lint/template_components.py --update-baseline`:\n'
        + '\n'.join(decreases)
    )


@pytest.mark.unit
def test_counts_the_markup_each_rule_covers() -> None:
    text = """
        <div class="modal-dialog modal-dialog-scrollable">
          <div class="modal-header"><h4 class="text-danger">Careful</h4></div>
          <div class="alert alert-warning">Note</div>
          <span class="badge text-bg-dark">1</span>
          <button class="text-nowrap white btn btn-primary"
                  data-bs-target="#modal-wrapper">
            <i class="bi-plus-lg pe-1"></i>Add
          </button>
          <button class="result-button white btn">1-0</button>
          <button class="dropdown-item">Item</button>
          <div class="admin-empty-state bg-light text-white">Empty</div>
        </div>
    """
    assert count_text(text) == {
        'modal-dialog': 1,
        'modal-header': 1,
        'warning-heading': 1,
        'note': 1,
        'badge': 1,
        'button': 2,
        'dead-white-class': 1,
        'modal-trigger': 1,
        'icon-spacing': 1,
        'menu-item': 1,
        'empty-state': 1,
        'fixed-colour': 2,
    }


@pytest.mark.unit
def test_similar_class_names_are_not_counted() -> None:
    text = (
        '<div class="modal-dialog-scrollable alert-dismissible btn-group '
        'badge-wrapper text-bg-dark"></div>'
    )
    assert count_text(text) == {}


@pytest.mark.unit
def test_compare_reports_growth_and_shrinkage() -> None:
    baseline = {'a.html': {'button': 2}, 'b.html': {'note': 1}}
    current = {'a.html': {'button': 3}, 'c.html': {'badge': 1}}
    increases, decreases = compare(current, baseline)
    assert [line.split(';')[0] for line in increases] == [
        'a.html: 3 button (baseline 2)',
        'c.html: 1 badge (baseline 0)',
    ]
    assert decreases == ['b.html: 0 note (baseline 1)']
