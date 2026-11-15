from datetime import date

import openpyxl
import pytest

from det import calc, reports
from det.models import Entry, Project
from det.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'shared')
    s.load()
    a = Project(name='Tower A', region='QLD', quoted_hours=10, reason_category='Good client')
    b = Project(name='Mezzanine & <frames>', region='NSW')
    for p in (a, b):
        s.save_project(p, new=True)
    for p, d, h, who in [(a, '2026-11-03', 8, 'Sam'), (a, '2026-11-10', 6, 'Lee'), (b, '2026-11-11', 2, 'Sam'),
                         (b, None, 3, 'Sam')]:
        s.save_entry(Entry(project_id=p.id, engineer=who, date=d, minutes=h * 60,
                           source='opening' if d is None else 'batch'), new=True)
    return s


def test_headline_matches_summary(store):
    period = calc.month_of(date(2026, 11, 14))
    report = reports.build_report(store, period)
    summary = calc.summarise(store.live_projects(), store.live_entries(), 220.0, period)
    assert report.headline['discounted_h'] == pytest.approx(summary.discounted_h) == pytest.approx(6.0)
    assert report.headline['amount'] == pytest.approx(1320.0)
    assert report.before_tracking_h == pytest.approx(3.0)
    assert len(report.project_rows) == 2 and len(report.entry_rows) == 3
    assert report.period_label == 'November 2026'


def test_xlsx(store, tmp_path):
    report = reports.build_report(store, calc.month_of(date(2026, 11, 14)))
    path = tmp_path / 'r.xlsx'
    reports.export_xlsx(report, path)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ['Summary', 'Projects', 'Engineers', 'Regions', 'Reasons', 'Entries']
    values = {row[0].value: row[1].value for row in wb['Summary'].iter_rows() if row[0].value}
    assert values['Discounted amount ($)'] == pytest.approx(1320.0)
    assert values['Discounted hours'] == pytest.approx(6.0)
    assert wb['Projects'].max_row == 3 and wb['Entries'].max_row == 4


def test_pdf(store, tmp_path):
    report = reports.build_report(store, calc.month_of(date(2026, 11, 14)))
    path = tmp_path / 'r.pdf'
    reports.export_pdf(report, path)
    data = path.read_bytes()
    assert data.startswith(b'%PDF') and len(data) > 1500


def test_empty_period(store, tmp_path):
    report = reports.build_report(store, calc.month_of(date(2020, 1, 1)))
    assert report.headline['discounted_h'] == 0 and report.entry_rows == []
    reports.export_xlsx(report, tmp_path / 'e.xlsx')
    reports.export_pdf(report, tmp_path / 'e.pdf')
    assert (tmp_path / 'e.pdf').stat().st_size > 0
