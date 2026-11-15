import openpyxl
import pytest

from det import importer
from det.store import Store

HEAD = ['Project Name', 'SF ID ', 'Region', 'Approved by', 'Engineer ', 'Additional Hours Spend',
        'Discounted Amount', 'Discounted Reason ', 'Remarks']


@pytest.fixture
def sheet(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws['H1'] = 'hr * 220'
    for i, text in enumerate(HEAD):
        ws.cell(row=2, column=2 + i, value=text)
    rows = [
        (1, 'Tower A', 'SF-1', 'qld', 'Pete', 'Sam', 3, None, 'As per email', 'CC: Vass'),
        (2, None, None, 'VIC', None, None, '=9+7+(0.15*7)+1', None, 'As per SF', None),
        (3, None, None, 'QLD', None, None, '15 & counting', None, None, None),
        (4, None, None, 'NSW', None, None, '=H6/220', None, 'IL4 ', 'Vass'),
        (5, None, None, 'NSW', None, None, None, None, 'Good client', None),
        (None, None, None, None, None, None, None, None, None, None),
        (None, None, None, 'nz', None, None, 0.75, None, None, None),
    ]
    for r, values in enumerate(rows, start=3):
        for c, value in enumerate(values, start=1):
            if value is not None:
                ws.cell(row=r, column=c, value=value)
    path = tmp_path / 'sheet.xlsx'
    wb.save(path)
    return path


def test_read_sheet(sheet):
    rows = importer.read_sheet(sheet)
    assert len(rows) == 6                                   # blank row skipped
    a, formula, text, ref, blank, unnumbered = rows
    assert (a.name, a.sf_id, a.region, a.approved_by, a.engineer) == ('Tower A', 'SF-1', 'QLD', 'Pete', 'Sam')
    assert a.hours == 3 and not a.needs_review and a.reason == 'As per email' and a.remarks == 'CC: Vass'
    assert formula.hours == pytest.approx(18.05) and not formula.needs_review and formula.name == 'Project 2'
    assert text.hours is None and text.needs_review and text.hours_text == '15 & counting'
    assert ref.hours is None and ref.needs_review and ref.hours_text == '=H6/220'
    assert blank.hours is None and not blank.needs_review
    assert unnumbered.name == 'Project (row 9)' and unnumbered.region == 'NZ' and unnumbered.hours == 0.75


def test_safe_arithmetic_only():
    assert importer.evaluate('=1+2*3') == 7
    assert importer.evaluate('=__import__("os")') is None
    assert importer.evaluate('=A1+2') is None
    assert importer.evaluate('=1/0') is None


def test_commit(sheet, tmp_path):
    store = Store(tmp_path / 'shared')
    store.load()
    rows = importer.read_sheet(sheet)
    rows[2].hours = 15.0                                    # the manager typed the figure in review
    created = importer.commit(rows, store, 'Manager')
    assert created == (6, 4)
    assert len(store.live_projects()) == 6 and len(store.live_entries()) == 4
    assert all(e.source == 'opening' and e.date is None for e in store.live_entries())
    tower = next(p for p in store.live_projects() if p.name == 'Tower A')
    assert tower.reason_detail == 'As per email' and tower.reason_category == 'Other'
    assert tower.lead_engineer == 'Sam' and tower.created_by == 'Manager'
    noted = next(p for p in store.live_projects() if p.name == 'Project 3')
    assert '15 & counting' in noted.remarks


def test_missing_header(tmp_path):
    wb = openpyxl.Workbook()
    wb.active['A1'] = 'nothing here'
    path = tmp_path / 'x.xlsx'
    wb.save(path)
    with pytest.raises(ValueError):
        importer.read_sheet(path)
