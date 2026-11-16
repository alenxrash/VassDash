"""Read the existing Discounted Engineering workbook. No Qt imports.

The sheet holds running totals with no dates, so each row becomes a project plus one undated
"opening balance" entry. Hours cells that are not plain numbers are flagged to be typed in;
nothing is guessed from text. The sheet's Discounted Amount is kept as the project's imported amount.
"""
from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass

from .models import Entry, Project
from .store import MAX_MINUTES

COLUMNS = {
    'project name': 'name', 'sf id': 'sf_id', 'region': 'region', 'approved by': 'approved_by',
    'engineer': 'engineer', 'additional hours spend': 'hours', 'additional hours spent': 'hours',
    'discounted amount': 'amount', 'discounted reason': 'reason', 'remarks': 'remarks',
}
# Reason text -> category, by plain keyword. Anything else stays 'Other' with the text kept as the detail.
CATEGORY_KEYWORDS = [
    ('Good client', ('good client', 'good customer')),
    ('Change of scope', ('change of scope', 'not included in quote')),
    ('Revised drawings', ('new drawings', 'revised drawings', 'drawings were provided')),
    ('Project size', ('project size', 'size')),
]


def categorise(reason: str) -> str:
    text = reason.casefold()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return 'Other'
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


@dataclass
class ImportRow:
    row_no: int
    name: str = ''
    sf_id: str = ''
    region: str = ''
    approved_by: str = ''
    engineer: str = ''
    hours: float | None = None
    hours_text: str = ''
    needs_review: bool = False
    amount: float | None = None
    reason: str = ''
    remarks: str = ''
    category: str = 'Other'


def evaluate(formula: str) -> float | None:
    """Value of a pure-arithmetic formula such as =9+7+(0.15*7)+1; None for anything else."""
    def walk(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError
    try:
        value = float(walk(ast.parse(formula.lstrip('=').strip(), mode='eval').body))
        return value if math.isfinite(value) else None
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError, RecursionError, MemoryError):
        return None


def _text(value) -> str:
    return '' if value is None else str(value).strip()


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def read_sheet(path) -> list[ImportRow]:
    import openpyxl
    formulas = openpyxl.load_workbook(path, data_only=False)
    cached = openpyxl.load_workbook(path, data_only=True)
    for ws in formulas.worksheets:
        header = next(((c.row, c.column) for row in ws.iter_rows(max_row=30) for c in row
                       if _text(c.value).casefold() == 'project name'), None)
        if header:
            break
    else:
        raise ValueError('No "Project Name" header was found in this workbook.')
    values = cached[ws.title]
    head_row = header[0]
    columns = {}
    for cell in ws[head_row]:
        field = COLUMNS.get(_text(cell.value).casefold())
        if field:
            columns.setdefault(field, cell.column)
    if 'hours' not in columns:
        raise ValueError('No "Additional Hours Spend" column was found.')
    rows = []
    last_column = max(columns.values())
    for r in range(head_row + 1, ws.max_row + 1):
        get = lambda field: ws.cell(row=r, column=columns[field]).value if field in columns else None
        if all(_text(get(field)) == '' for field in columns):
            continue
        item = ImportRow(row_no=r, name=_text(get('name')), sf_id=_text(get('sf_id')),
                         region=_text(get('region')).upper(), approved_by=_text(get('approved_by')),
                         engineer=_text(get('engineer')), reason=_text(get('reason')), remarks=_text(get('remarks')))
        notes: list[str] = []
        if not item.name:
            number = ws.cell(row=r, column=1).value if columns.get('name', 1) > 1 else None
            item.name = f'Project {int(number)}' if _number(number) is not None and number else f'Project (row {r})'
        raw = get('hours')
        if isinstance(raw, str) and raw.strip().startswith('='):
            item.hours_text = raw.strip()
            value = evaluate(raw)
            if value is None:
                value = _number(values.cell(row=r, column=columns['hours']).value) or None
            item.hours = value if value is not None and value >= 0 else None
            item.needs_review = item.hours is None
        elif _number(raw) is not None:
            item.hours = float(raw)
        elif _text(raw):
            item.hours_text = _text(raw)
            item.needs_review = True
        if 'amount' in columns:
            money = get('amount')
            if isinstance(money, str) and money.strip().startswith('='):
                value = evaluate(money)
                item.amount = value if value is not None else _number(values.cell(row=r, column=columns['amount']).value)
            elif _number(money) is not None:
                item.amount = float(money)
            elif _text(money):
                notes.append(f'Imported amount note: {_text(money)}')
        # Loose notes typed to the right of the table belong with the row.
        for column in range(last_column + 1, ws.max_column + 1):
            extra = _text(ws.cell(row=r, column=column).value)
            if extra:
                notes.append(extra)
        item.remarks = '; '.join(part for part in [item.remarks] + notes if part)
        item.category = categorise(item.reason)
        rows.append(item)
    return rows


def commit(rows, store, user: str) -> tuple[int, int]:
    """Create a project per row and an undated opening entry where hours were given. Returns (projects, entries)."""
    for row in rows:
        if row.hours is not None and not 0 <= row.hours * 60 <= MAX_MINUTES * 365:
            raise ValueError(f'Row {row.row_no}: hours are out of range.')
        if row.amount is not None and not 0 <= row.amount < 1e9:
            raise ValueError(f'Row {row.row_no}: amount is out of range.')
        if not row.name.strip():
            raise ValueError(f'Row {row.row_no}: project name is required.')
    projects = entries = 0
    for row in rows:
        remarks = row.remarks
        if row.hours_text and not row.hours_text.startswith('='):
            remarks = '; '.join(part for part in (remarks, f'Imported hours note: {row.hours_text}') if part)
        project = Project(name=row.name.strip(), sf_id=row.sf_id, region=row.region, approved_by=row.approved_by,
                          lead_engineer=row.engineer, reason_category=row.category or 'Other',
                          reason_detail=row.reason, remarks=remarks, created_by=user, opening_amount=row.amount)
        store.save_project(project, new=True)
        projects += 1
        minutes = round((row.hours or 0) * 60)
        if minutes > 0:
            store.save_entry(Entry(project_id=project.id, engineer=row.engineer or user, date=None,
                                   minutes=minutes, source='opening', note='Imported from Excel'), new=True)
            entries += 1
    return projects, entries
