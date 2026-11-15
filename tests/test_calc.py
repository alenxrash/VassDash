from datetime import date

import pytest

from det import calc
from det.models import Entry, Project


def entry(p, d, hours, engineer='Sam', created='2026-01-01T00:00:00', **kw):
    return Entry(project_id=p.id, engineer=engineer, date=d, minutes=round(hours * 60), created_at=created, **kw)


def test_financial_year_boundaries():
    fy = calc.fy_of(date(2026, 6, 30))
    assert (fy.start, fy.end, fy.label) == (date(2025, 7, 1), date(2026, 6, 30), 'FY 2025-26')
    fy = calc.fy_of(date(2026, 7, 1))
    assert (fy.start, fy.end, fy.label) == (date(2026, 7, 1), date(2027, 6, 30), 'FY 2026-27')


def test_week_and_month():
    w = calc.week_of(date(2026, 11, 14))
    assert (w.start, w.end) == (date(2026, 11, 9), date(2026, 11, 15))
    m = calc.month_of(date(2026, 2, 10))
    assert (m.start, m.end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_entry_straddles_quote():
    p = Project(name='A', quoted_hours=10)
    es = [entry(p, '2026-11-02', 6), entry(p, '2026-11-09', 6)]
    slices = calc.attribute(p, es)
    assert [s.discounted_minutes for s in slices] == [0, 120]


def test_no_quote_all_discounted():
    p = Project(name='A')
    slices = calc.attribute(p, [entry(p, '2026-11-02', 3)])
    assert slices[0].discounted_minutes == 180


def test_opening_balance_consumes_quote_first():
    p = Project(name='A', quoted_hours=10)
    es = [entry(p, '2026-11-10', 5), entry(p, None, 8, source='opening')]
    row = calc.project_totals(p, es, 220.0, calc.month_of(date(2026, 11, 1)))
    assert row.logged_h == 13 and row.discounted_h == 3
    assert row.period_discounted_h == 3 and row.period_amount == 660.0
    assert row.opening_h == 8
    all_time = calc.project_totals(p, es, 220.0, calc.all_time())
    assert all_time.period_logged_h == 13 and all_time.period_discounted_h == 3


def test_over_pct():
    p = Project(name='A', quoted_hours=10)
    assert calc.project_totals(p, [entry(p, '2026-11-02', 15)], 220.0).over_pct == 50.0
    under = calc.project_totals(p, [entry(p, '2026-11-02', 8)], 220.0)
    assert under.over_pct == -20.0 and under.discounted_h == 0
    for quote in (None, 0):
        q = Project(name='B', quoted_hours=quote)
        assert calc.project_totals(q, [entry(q, '2026-11-02', 4)], 220.0).over_pct is None


def test_deleted_entries_ignored():
    p = Project(name='A')
    es = [entry(p, '2026-11-02', 4), entry(p, '2026-11-03', 9, deleted=True)]
    assert calc.project_totals(p, es, 220.0).logged_h == 4


def test_summary():
    a = Project(name='A', region='QLD', quoted_hours=10, reason_category='Good client')
    b = Project(name='B', region='NSW', reason_category='Change of scope')
    gone = Project(name='Gone', deleted=True)
    es = [entry(a, '2026-11-03', 8, 'Sam'), entry(a, '2026-11-10', 6, 'Lee'),
          entry(b, '2026-11-11', 2, 'Sam'), entry(b, '2026-10-01', 5, 'Sam'),
          entry(b, None, 3, 'Sam', source='opening'), entry(gone, '2026-11-11', 50)]
    s = calc.summarise([a, b, gone], es, 220.0, calc.month_of(date(2026, 11, 14)))
    assert s.discounted_h == pytest.approx(6.0)          # 4 from A (after quote) + 2 from B
    assert s.amount == pytest.approx(1320.0)
    assert s.by_region == {'QLD': pytest.approx(4.0), 'NSW': pytest.approx(2.0)}
    assert s.by_engineer == {'Lee': pytest.approx(4.0), 'Sam': pytest.approx(2.0)}
    assert s.by_reason == {'Good client': pytest.approx(4.0), 'Change of scope': pytest.approx(2.0)}
    assert (s.over_count, s.quoted_count) == (1, 1) and s.avg_over_pct == pytest.approx(40.0)
    assert s.before_tracking_h == pytest.approx(3.0)
    assert sum(v for _, v in s.trend) == pytest.approx(6.0)
    everything = calc.summarise([a, b, gone], es, 220.0, calc.all_time())
    assert everything.discounted_h == pytest.approx(14.0)   # 4 + (2 + 5 + 3)
    only_sam = calc.summarise([a, b], es, 220.0, calc.month_of(date(2026, 11, 14)), engineer='Sam')
    assert only_sam.discounted_h == pytest.approx(2.0)
    qld = calc.summarise([a, b], es, 220.0, calc.all_time(), region='QLD')
    assert [r.project.name for r in qld.rows] == ['A']


def test_summary_empty():
    s = calc.summarise([], [], 220.0, calc.all_time())
    assert s.discounted_h == 0 and s.rows == [] and s.trend == [] and s.avg_over_pct is None
