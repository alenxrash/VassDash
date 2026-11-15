"""Period reports: figures, then Excel and PDF export. No Qt imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from xml.sax.saxutils import escape

from . import calc


@dataclass
class Report:
    title: str
    period_label: str
    generated: str
    rate: float
    headline: dict
    project_rows: list = field(default_factory=list)    # name, sf_id, region, quoted_h, logged_h(period), discounted_h(period), amount, over_pct
    engineer_rows: list = field(default_factory=list)   # label, hours, amount
    region_rows: list = field(default_factory=list)
    reason_rows: list = field(default_factory=list)
    entry_rows: list = field(default_factory=list)      # date, project, engineer, revision, note, hours, discounted_h
    before_tracking_h: float = 0.0
    dated: bool = True


def build_report(store, period: calc.Period, rate: float | None = None, region: str | None = None,
                 engineer: str | None = None) -> Report:
    rate = store.config.rate if rate is None else rate
    s = calc.summarise(store.live_projects(), store.live_entries(), rate, period, region, engineer)
    split = lambda totals: [(label, hours, hours * rate) for label, hours in totals.items()]
    entries = []
    for row in s.rows:
        for piece in row.period_slices:
            e = piece.entry
            entries.append((e.date or '', row.project.name, e.engineer, e.revision, e.note, e.hours, piece.discounted_h))
    entries.sort(key=lambda r: (r[0], r[1].casefold()))
    return Report(
        title='Discounted Engineering Report', period_label=period.label,
        generated=datetime.now().strftime('%d/%m/%Y %H:%M'), rate=rate, dated=period.dated,
        headline={'discounted_h': s.discounted_h, 'amount': s.amount, 'logged_h': s.logged_h,
                  'projects': len(s.rows), 'over_count': s.over_count, 'quoted_count': s.quoted_count,
                  'avg_over_pct': s.avg_over_pct},
        project_rows=[(r.project.name, r.project.sf_id, r.project.region, r.quoted_h, r.period_logged_h,
                       r.period_discounted_h, r.period_amount, r.over_pct) for r in s.rows],
        engineer_rows=split(s.by_engineer), region_rows=split(s.by_region), reason_rows=split(s.by_reason),
        entry_rows=entries, before_tracking_h=s.before_tracking_h)


def headline_lines(report: Report) -> list[tuple[str, object]]:
    h = report.headline
    lines = [('Discounted hours', round(h['discounted_h'], 2)), ('Discounted amount ($)', round(h['amount'], 2)),
             ('Hours logged', round(h['logged_h'], 2)), ('Projects with activity', h['projects']),
             ('Projects over quote', f"{h['over_count']} of {h['quoted_count']} quoted"),
             ('Average over quote (%)', h['avg_over_pct'] if h['avg_over_pct'] is not None else 'n/a'),
             ('Rate ($/h)', report.rate)]
    if report.dated and report.before_tracking_h:
        lines.append(('Before tracking, undated (h, not in period)', round(report.before_tracking_h, 2)))
    return lines


def _date(iso: str) -> str:
    return f'{iso[8:10]}/{iso[5:7]}/{iso[0:4]}' if iso else 'Undated'


def export_xlsx(report: Report, path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    bold = Font(bold=True)

    def sheet(title, headers, rows, widths, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(headers)
        for cell in ws[1]:
            cell.font = bold
        for row in rows:
            ws.append(list(row))
        for index, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(index)].width = width
        ws.freeze_panes = 'A2'
        return ws

    ws = wb.active
    ws.title = 'Summary'
    ws.append([report.title])
    ws['A1'].font = Font(bold=True, size=14)
    ws.append(['Period', report.period_label])
    ws.append(['Generated', report.generated])
    ws.append([])
    for label, value in headline_lines(report):
        ws.append([label, value])
    ws.column_dimensions['A'].width = 44
    ws.column_dimensions['B'].width = 24
    r2 = lambda v: None if v is None else round(v, 2)
    sheet('Projects', ['Project', 'SF ID', 'Region', 'Quoted h', 'Logged h (period)', 'Discounted h (period)',
                       'Discounted $', 'Over quote % (to date)'],
          [(n, sf, reg, r2(q), r2(lg), r2(d), r2(a), o) for n, sf, reg, q, lg, d, a, o in report.project_rows],
          [38, 14, 10, 10, 18, 20, 14, 22])
    for title, rows in (('Engineers', report.engineer_rows), ('Regions', report.region_rows),
                        ('Reasons', report.reason_rows)):
        sheet(title, [title[:-1], 'Discounted h', 'Discounted $'], [(l, r2(h), r2(a)) for l, h, a in rows], [30, 14, 14])
    sheet('Entries', ['Date', 'Project', 'Engineer', 'Revision', 'Note', 'Hours', 'Discounted h'],
          [(_date(d), p, e, rev, note, r2(h), r2(dh)) for d, p, e, rev, note, h, dh in report.entry_rows],
          [12, 38, 18, 10, 40, 10, 14])
    wb.save(path)


def export_pdf(report: Report, path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    body = ParagraphStyle('cell', parent=styles['BodyText'], fontSize=8.5, leading=10.5)
    head = ParagraphStyle('head', parent=body, fontName='Helvetica-Bold', textColor=colors.HexColor('#5B6474'))
    h1 = ParagraphStyle('h1', parent=styles['Title'], fontSize=18, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=11.5, spaceBefore=12, spaceAfter=5)
    muted = ParagraphStyle('muted', parent=body, textColor=colors.HexColor('#5B6474'), fontSize=9.5)
    para = lambda value, style=body: Paragraph(escape('' if value is None else str(value)), style)
    num = lambda v, places=2: '' if v is None else f'{v:,.{places}f}'

    def table(headers, rows, widths):
        data = [[para(h, head) for h in headers]] + [[para(c) for c in row] for row in rows]
        if not rows:
            data.append([para('No data for this period.')] + [''] * (len(headers) - 1))
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.HexColor('#CDD3DC')),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#E4E7EC')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        return t

    h = report.headline
    story = [para(report.title, h1), para(f'{report.period_label}  ·  generated {report.generated}', muted), Spacer(1, 8)]
    story.append(table(['Measure', 'Value'], [
        ('Discounted hours', f"{num(h['discounted_h'])} h"), ('Discounted amount', f"${num(h['amount'])}"),
        ('Hours logged', f"{num(h['logged_h'])} h"), ('Projects with activity', h['projects']),
        ('Projects over quote', f"{h['over_count']} of {h['quoted_count']} quoted"),
        ('Average over quote', 'n/a' if h['avg_over_pct'] is None else f"+{h['avg_over_pct']:.0f}%"),
        ('Rate', f"${num(report.rate)}/h")], [80, 60]))
    if report.dated and report.before_tracking_h:
        story.append(Spacer(1, 6))
        story.append(para(f'Before tracking: {num(report.before_tracking_h)} h of undated opening balances are not '
                          f'in this period. They count in project totals and all-time figures.', muted))
    story.append(para('By project', h2))
    story.append(table(['Project', 'SF ID', 'Region', 'Quoted h', 'Logged h', 'Discounted h', 'Discounted $', 'Over quote'],
                       [(n, sf, reg, num(q), num(lg), num(d), f'${num(a)}', '' if o is None else f'{o:+.0f}%')
                        for n, sf, reg, q, lg, d, a, o in report.project_rows], [80, 28, 20, 22, 22, 28, 30, 26]))
    for title, rows in (('By engineer', report.engineer_rows), ('By region', report.region_rows),
                        ('By reason', report.reason_rows)):
        story.append(para(title, h2))
        story.append(table([title[3:].capitalize(), 'Discounted h', 'Discounted $'],
                           [(l, num(hh), f'${num(a)}') for l, hh, a in rows], [90, 35, 35]))
    story.append(para('Entries', h2))
    story.append(table(['Date', 'Project', 'Engineer', 'Rev', 'Note', 'Hours', 'Discounted h'],
                       [(_date(d), p, e, rev, note, num(hh), num(dh)) for d, p, e, rev, note, hh, dh in report.entry_rows],
                       [22, 68, 34, 16, 70, 20, 26]))
    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=16 * mm, rightMargin=16 * mm,
                      topMargin=14 * mm, bottomMargin=14 * mm, title=f'{report.title} - {report.period_label}').build(story)
