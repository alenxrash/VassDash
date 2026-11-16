"""Periods and discounted-engineering arithmetic. No Qt imports.

Rule for overrun: a project's entries are taken in order (undated opening balances first, then by
date and creation time). The quote is used up in that order, and only the part of an entry that
falls after the quote has run out is discounted. With no quote, every logged hour is discounted.

Rule for dollars: discounted hours are valued at the rate. Where a project carries an imported
amount (Project.opening_amount), that figure replaces the rate for the project's imported hours,
because the old sheet's dollar column was not always hours x rate. An imported amount has no date,
so it counts in project totals and All time, never in a dated period.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import Entry, Project, merge_names


@dataclass(frozen=True)
class Period:
    label: str
    start: date | None = None
    end: date | None = None

    @property
    def dated(self) -> bool:
        return self.start is not None

    def contains(self, iso: str | None) -> bool:
        if not self.dated:
            return True
        if not iso:
            return False
        try:
            return self.start <= date.fromisoformat(iso) <= self.end
        except ValueError:
            return False


def all_time() -> Period:
    return Period('All time')


def week_of(day: date) -> Period:
    monday = day - timedelta(days=day.weekday())
    return Period(f'Week of {monday.day} {monday:%b %Y}', monday, monday + timedelta(days=6))


def month_of(day: date) -> Period:
    start = day.replace(day=1)
    following = (start + timedelta(days=32)).replace(day=1)
    return Period(f'{start:%B %Y}', start, following - timedelta(days=1))


def fy_of(day: date, start_month: int = 7) -> Period:
    year = day.year if day.month >= start_month else day.year - 1
    start = date(year, start_month, 1)
    end = date(year + 1, start_month, 1) - timedelta(days=1)
    label = f'FY {year}-{(year + 1) % 100:02d}' if start_month != 1 else f'{year}'
    return Period(label, start, end)


def custom(start: date, end: date) -> Period:
    if end < start:
        start, end = end, start
    return Period(f'{start.day} {start:%b %Y} to {end.day} {end:%b %Y}', start, end)


@dataclass
class Slice:
    entry: Entry
    minutes: int
    discounted_minutes: float

    @property
    def discounted_h(self) -> float:
        return self.discounted_minutes / 60


def attribute(project: Project, entries) -> list[Slice]:
    live = sorted((e for e in entries if not e.deleted),
                  key=lambda e: (bool(e.date), e.date or '', e.created_at, e.id))
    quoted = project.quoted_hours
    if not quoted or quoted <= 0:
        return [Slice(e, e.minutes, e.minutes) for e in live]
    remaining = quoted * 60
    slices = []
    for e in live:
        within = min(remaining, e.minutes)
        remaining -= within
        over = e.minutes - within
        slices.append(Slice(e, e.minutes, int(over) if float(over).is_integer() else over))
    return slices


@dataclass
class ProjectRow:
    project: Project
    logged_h: float = 0.0
    quoted_h: float | None = None
    discounted_h: float = 0.0
    amount: float = 0.0
    over_pct: float | None = None
    opening_h: float = 0.0
    period_logged_h: float = 0.0
    period_discounted_h: float = 0.0
    period_amount: float = 0.0
    slices: list = field(default_factory=list)
    period_slices: list = field(default_factory=list)
    engineer_amounts: dict = field(default_factory=dict)     # dollars in the period, by engineer


def _imported_shares(project: Project, slices) -> dict:
    """Who an imported amount belongs to: split by imported hours, else the lead engineer."""
    if project.opening_amount is None:
        return {}
    opening = [s for s in slices if s.entry.source == 'opening']
    total = sum(s.minutes for s in opening)
    if total <= 0:
        return {project.lead_engineer or 'Unassigned': project.opening_amount}
    shares: dict = defaultdict(float)
    for s in opening:
        shares[s.entry.engineer or 'Unassigned'] += project.opening_amount * s.minutes / total
    return dict(shares)


def project_totals(project: Project, entries, rate: float, period: Period | None = None,
                   engineer: str | None = None) -> ProjectRow:
    period = period or all_time()
    slices = attribute(project, entries)
    logged = sum(s.minutes for s in slices) / 60
    quoted = project.quoted_hours if project.quoted_hours and project.quoted_hours > 0 else None
    discounted = sum(s.discounted_minutes for s in slices) / 60
    imported = project.opening_amount is not None
    # Hours valued at the rate: everything, except imported hours when an imported amount covers them.
    at_rate = lambda group: [s for s in group if not (imported and s.entry.source == 'opening')]
    dollars = lambda group: sum(s.discounted_minutes for s in at_rate(group)) / 60 * rate
    shares = _imported_shares(project, slices)
    wanted = engineer.casefold() if engineer else None
    chosen = [s for s in slices if wanted is None or s.entry.engineer.casefold() == wanted]
    in_period = [s for s in chosen if period.contains(s.entry.date)]
    by_engineer: dict = defaultdict(float)
    for s in at_rate(in_period):
        by_engineer[s.entry.engineer or 'Unassigned'] += s.discounted_minutes / 60 * rate
    if not period.dated:
        for name, share in shares.items():
            if wanted is None or name.casefold() == wanted:
                by_engineer[name] += share
    period_discounted = sum(s.discounted_minutes for s in in_period) / 60
    return ProjectRow(
        project=project, logged_h=logged, quoted_h=quoted, discounted_h=discounted,
        amount=dollars(slices) + (project.opening_amount or 0.0),
        over_pct=round((logged - quoted) / quoted * 100, 1) if quoted else None,
        opening_h=sum(s.minutes for s in slices if not s.entry.date) / 60,
        period_logged_h=sum(s.minutes for s in in_period) / 60,
        period_discounted_h=period_discounted, period_amount=sum(by_engineer.values()),
        slices=chosen, period_slices=in_period, engineer_amounts=dict(by_engineer))


@dataclass
class Summary:
    period: Period
    rate: float
    rows: list = field(default_factory=list)
    discounted_h: float = 0.0
    logged_h: float = 0.0
    amount: float = 0.0
    over_count: int = 0
    quoted_count: int = 0
    avg_over_pct: float | None = None
    by_region: dict = field(default_factory=dict)
    by_engineer: dict = field(default_factory=dict)
    by_reason: dict = field(default_factory=dict)
    trend: list = field(default_factory=list)
    before_tracking_h: float = 0.0
    amount_by_region: dict = field(default_factory=dict)
    amount_by_engineer: dict = field(default_factory=dict)
    amount_by_reason: dict = field(default_factory=dict)


def _ranked(totals: dict) -> dict:
    return {k: v for k, v in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])) if v > 0}


def _trend(period: Period, slices) -> list:
    dated = [(date.fromisoformat(s.entry.date), s.discounted_minutes / 60) for s in slices if s.entry.date]
    if period.dated:
        start, end = period.start, period.end
    elif dated:
        start, end = min(d for d, _ in dated), max(d for d, _ in dated)
    else:
        return []
    span = (end - start).days + 1
    buckets: dict = {}
    if span <= 14:
        key = lambda d: d
        label = lambda d: f'{d:%a} {d.day}'
        step = start
        while step <= end:
            buckets[step] = 0.0
            step += timedelta(days=1)
    elif span <= 93:
        key = lambda d: d - timedelta(days=d.weekday())
        label = lambda d: f'{d.day} {d:%b}'
        step = key(start)
        while step <= end:
            buckets[step] = 0.0
            step += timedelta(days=7)
    else:
        key = lambda d: d.replace(day=1)
        label = lambda d: f'{d:%b %y}'
        step = key(start)
        while step <= end:
            buckets[step] = 0.0
            step = (step + timedelta(days=32)).replace(day=1)
    for day, hours in dated:
        buckets[key(day)] = buckets.get(key(day), 0.0) + hours
    return [(label(k), v) for k, v in sorted(buckets.items())]


def summarise(projects, entries, rate: float, period: Period | None = None, region: str | None = None,
              engineer: str | None = None) -> Summary:
    period = period or all_time()
    grouped = defaultdict(list)
    for e in entries:
        if not e.deleted:
            grouped[e.project_id].append(e)
    summary = Summary(period=period, rate=rate)
    regions, engineers, reasons = defaultdict(float), defaultdict(float), defaultdict(float)
    region_d, engineer_d, reason_d = defaultdict(float), defaultdict(float), defaultdict(float)
    period_slices, over = [], []
    for project in projects:
        if project.deleted or (region and project.region != region):
            continue
        row = project_totals(project, grouped.get(project.id, []), rate, period, engineer)
        if (period.dated or engineer) and not row.period_slices and row.period_amount <= 0:
            continue
        summary.rows.append(row)
        summary.discounted_h += row.period_discounted_h
        summary.logged_h += row.period_logged_h
        regions[project.region or 'No region'] += row.period_discounted_h
        reasons[project.reason_category or 'Other'] += row.period_discounted_h
        region_d[project.region or 'No region'] += row.period_amount
        reason_d[project.reason_category or 'Other'] += row.period_amount
        for name, dollars in row.engineer_amounts.items():
            engineer_d[name] += dollars
        summary.amount += row.period_amount
        for s in row.period_slices:
            engineers[s.entry.engineer or 'Unassigned'] += s.discounted_minutes / 60
        summary.before_tracking_h += sum(s.discounted_minutes for s in row.slices if not s.entry.date) / 60
        period_slices.extend(row.period_slices)
        if row.quoted_h:
            summary.quoted_count += 1
            if row.logged_h > row.quoted_h:
                over.append(row.over_pct)
    summary.rows.sort(key=lambda r: (-r.period_amount, -r.period_discounted_h, -r.period_logged_h, r.project.name.casefold()))
    summary.over_count = len(over)
    summary.avg_over_pct = round(sum(over) / len(over), 1) if over else None
    summary.by_region, summary.by_engineer, summary.by_reason = (
        _ranked(regions), _ranked(merge_names(engineers)), _ranked(reasons))
    summary.amount_by_region, summary.amount_by_engineer, summary.amount_by_reason = (
        _ranked(region_d), _ranked(merge_names(engineer_d)), _ranked(reason_d))
    summary.trend = _trend(period, period_slices)
    return summary
