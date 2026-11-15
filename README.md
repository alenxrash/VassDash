# Discounted Engineering Tracker (revision 3)

A Windows desktop app for tracking discounted engineering: hours spent beyond a project's quote, costed at
a set rate (default $220/h). Engineers log hours with a timer or a batch form. The manager gets a dashboard
and period reports. It replaces the Discounted Engineering Excel sheet.

## What changed in revision 3

The pop-out timer is replaced by a floating timer widget.

- **Docked (default):** it floats in the bottom-right corner over every page, so the timer is reachable from
  the dashboard or reports without going back to Log time.
- **Detached:** click Detach and it becomes its own always-on-top window that stays visible over other
  programs. Click Dock to put it back.
- **Move and resize:** drag the body to move it; drag any edge or corner to resize. The clock grows and
  shrinks with it. It cannot be dragged off the window (docked) or off the screen (detached).
- **Controls:** pick a project and Start; then Pause, Resume and Stop (Stop saves the entry). Rev and note
  are still entered on the Log time timer card, which stays in step with the widget.
- **Hide / Show widget:** Hide on the widget, and a Show widget button on the Log time timer card.
- Position, size, docked or detached, and hidden or shown are remembered per PC.

Limits: the detached window has square corners (rounded corners would need a see-through window, which is
unreliable for this kind of window on Windows). While a dialog box is open in the app, the widget does not
respond until the dialog is closed.

## What changed in revision 2

Interface only; data, calculations and file formats are unchanged, so revision 1 data opens as is.

- New look: deep navy background, rounded cards, pill buttons and inputs, blue accent, round icon navigation,
  a top bar with the page trail and who is signed in, and a right-hand column of summary cards.
- Log time gains a "This week" card (hours per day) and a "My projects" card.
- The dashboard trend lights and labels its highest bar.
- Dark is now the default theme. A light version of the same design is in Settings.

Not reproduced from the reference picture: background blur behind the cards and a photo backdrop. Qt
desktop widgets cannot blur what is behind them cheaply, so cards use gradients instead.

## Build the .exe

1. Install Python 3.10 or newer on a Windows PC.
2. Double-click `build_exe.bat`. It creates a private build environment, installs the dependencies and
   produces `dist\Discounted Engineering Tracker.exe`.
3. Give that one file to each person.

To run from source instead: `pip install -r requirements.txt`, then `run_app.bat` (or `python app.py`).

## First run

Each person enters their name and picks the **shared team folder** in Dropbox. Everyone must pick the same
folder. An empty folder is fine; the app creates `Projects`, `Entries` and `config.json` in it.

## How it works

- **Log time** (everyone): start/stop timer with pause and a floating widget that can be detached; batch entry of
  several rows at once; your own entries for the week, with edit and delete. Engineers can add a project
  (name, SF ID, region) so logging is never blocked.
- **Manager sign in** (bottom left): the first person to click it sets the passcode. It unlocks Dashboard,
  Projects, Reports and the shared settings.
- **Dashboard**: discounted hours and dollars, projects over quote, top projects, over-quote percentage,
  trend, and splits by region, engineer and reason. Double-click a project for the entries behind it.
- **Reports**: week, month, financial year, custom range or all time; preview; export to PDF or Excel.
- **Settings > Import from Excel** (manager): reads the old sheet. Each row becomes a project with an
  undated "opening balance". Hours cells that were not plain numbers are highlighted to be typed in.

## Rules the figures follow

- Quoted hours set: discounted hours = logged minus quoted (never below zero); over quote % =
  (logged - quoted) / quoted.
- No quote: every logged hour is discounted and no percentage is shown.
- Amount = discounted hours x rate.
- For a period, the quote is used up in date order (opening balances first). Only hours logged after the
  quote ran out count as discounted, in the period they were logged.
- Undated opening balances count in project totals and All time, and are listed as "before tracking" in
  dated periods.
- Financial year starts 1 July (changeable). Weeks run Monday to Sunday.

## Data and limits

- Shared data is one small JSON file per project and per entry, so two people logging at once never write
  the same file. Deleting marks a record deleted; it does not remove the file.
- The app re-reads the folder every 30 seconds. Dropbox "conflicted copy" files and unreadable files are
  left out of totals and reported in a red banner.
- **The manager passcode is not security.** It hides screens. Anyone who can open the shared folder can
  read or edit the files. Engineers seeing only their own entries is likewise enforced by the screens only.
- Your name and the running timer are stored per PC in `%LOCALAPPDATA%\DiscountedEngineeringTracker`.

## Tested and not tested

Tested (60 automated tests, run on Linux with Python 3.13 and PySide6 6.12): storage, calculations, period
boundaries, timer, Excel import (including the real workbook's layout), PDF and Excel export, and
interface smoke tests of every page in a headless window.

Not tested: the Windows .exe build, behaviour on real Dropbox sync between several PCs, the detached
widget staying on top of other programs, and high-DPI scaling on Windows. Check these on a Windows PC before relying on the app.

Not in this revision: a system-tray icon (the floating widget covers the same need), duplicate detection on
import, and per-project or dated rates.

Run the tests with `python -m pytest -q` (needs `pip install pytest`).
