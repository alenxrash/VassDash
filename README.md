# Discounted Engineering Tracker (revision 4)

A Windows desktop app for tracking discounted engineering: hours spent beyond a project's quote, costed at
a set rate (default $220/h), plus dollar amounts carried over from the old Excel sheet. People log hours
with a timer or a batch form; the dashboard and reports show where the discount is going. Everyone sees the
same screens.

## What changed in revision 4

- **One view for everyone.** The manager sign-in and passcode are gone. Dashboard, Reports and shared
  settings are open to all, and anyone can edit any project or entry.
- **Projects tab removed.** Add a project from Log time (New project). Open, edit, close or delete one by
  double-clicking it in the Dashboard's project table.
- **Imported dollar amounts.** The old sheet's Discounted Amount column is now imported and kept as given.
  It was not always hours x rate (some rows carry a fixed discount, some have dollars and no hours), so
  each project can hold an "imported amount". See "Rules the figures follow".
- **Dashboard ranks by dollars.** Top projects and the region, engineer and reason splits are in dollars,
  so projects with an amount and no hours still appear.
- **Excel import** reads the amount column, puts loose notes typed beside the table into remarks, and
  suggests a reason category from plain keywords (shown in the review table before anything is saved).
- Engineer names that differ only by letter case are counted as one person.

Revision 3 added the floating timer widget (dock over every page, detach to an always-on-top window, drag,
resize). Revision 2 was the navy, rounded-card look.

## Build the .exe

1. Install Python 3.10 or newer on a Windows PC.
2. Double-click `build_exe.bat`. It creates a private build environment, installs the dependencies and
   produces `dist\Discounted Engineering Tracker.exe`.
3. Give that one file to each person.

To run from source instead: `pip install -r requirements.txt`, then `run_app.bat` (or `python app.py`).

## First run

Each person enters their name and picks the **shared team folder** in Dropbox. Everyone must pick the same
folder. An empty folder is fine; the app creates `Projects`, `Entries` and `config.json` in it.

Project data is not part of this repository. It lives only in the shared folder.

## How it works

- **Log time:** start/stop timer with pause and a floating widget that can be detached; batch entry of
  several rows at once; your own entries for the week, with edit and delete; New project.
- **Dashboard:** discounted hours and dollars, projects over quote, top projects, over-quote percentage,
  trend, and splits by region, engineer and reason. Double-click a project for its entries, to edit it or
  to delete it.
- **Reports:** week, month, financial year, custom range or all time; preview; export to PDF or Excel.
- **Settings:** your name, the shared folder and theme; the rate, financial-year start, regions and reason
  categories; and Import from Excel.

## Rules the figures follow

- Quoted hours set: discounted hours = logged minus quoted (never below zero); over quote % =
  (logged - quoted) / quoted.
- No quote: every logged hour is discounted and no percentage is shown.
- Dollars = discounted hours x rate, with one exception: where a project has an imported amount, that
  figure replaces the rate for the project's imported hours. Hours logged in the app afterwards are added
  at the rate.
- An imported amount with no imported hours is credited to the project's lead engineer; with hours, it is
  split between engineers in proportion to those hours.
- For a period, the quote is used up in date order (opening balances first). Only hours logged after the
  quote ran out count as discounted, in the period they were logged.
- Undated opening balances and imported amounts count in project totals and All time. They are not in any
  dated period (week, month, financial year), because the old sheet recorded no dates.
- Financial year starts 1 July (changeable). Weeks run Monday to Sunday.

## Data and limits

- Shared data is one small JSON file per project and per entry, so two people logging at once never write
  the same file. Deleting marks a record deleted; it does not remove the file.
- The app re-reads the folder every 30 seconds. Dropbox "conflicted copy" files and unreadable files are
  left out of totals and reported in a red banner.
- There is no access control. Anyone with the app and the shared folder can see and change everything.
- Your name, the running timer and the widget's position are stored per PC in
  `%LOCALAPPDATA%\DiscountedEngineeringTracker`.
- The detached timer has square corners, and does not respond while a dialog box is open in the app.
- Import does not detect duplicates of existing projects; it warns and asks first.

## Tested and not tested

Tested (66 automated tests, run on Linux with Python 3.13 and PySide6 6.12): storage, calculations
including imported amounts, period boundaries, timer, Excel import, PDF and Excel export, the floating
widget, and interface smoke tests of every page in a headless window.

Not tested: the Windows .exe build, behaviour on real Dropbox sync between several PCs, the detached
widget staying on top of other programs, and high-DPI scaling on Windows. Check these on a Windows PC
before relying on the app.

Run the tests with `python -m pytest -q` (needs `pip install pytest`).
