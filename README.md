# Budget Tracker (revision 6)

Budget Tracker tracks discounted engineering: hours spent beyond a project's quote, costed at a set rate
(default $220/h), plus dollar amounts carried over from the old Excel sheet. It is a Windows desktop app
with a timer widget that sits on the desktop. Everyone sees the same screens.

## Using it

There is nothing to set up. Open `Budget Tracker.exe` and:

1. Pick a project in the timer widget (or type a new name to create one) and press **Start**.
2. **Pause**, **Resume** and **Stop** from the widget. Stop saves the time.

Or add hours without the timer: on **My time**, choose the project, type the hours and press **Add**.

## What changed in revision 6

- **Renamed to Budget Tracker** (was VassDash), with a new mark and icon. The exe is now
  `Budget Tracker.exe`. Settings and team data are unchanged and carry over. A "Start with Windows"
  entry made by the old exe is switched to the new one the first time Budget Tracker starts.
- **No user profile in the top bar.** The name and initials badge are gone. Your name still comes from
  Windows and is still recorded on your entries; change it in Settings if needed.

## What changed in revision 5

- **The timer is its own desktop widget.** It is a separate always-on-top window, not part of the main
  window. Closing the main window leaves the widget and the timer running. Drag it anywhere, resize it
  from any edge, right-click it for Always on top, Hide and Quit. A tray icon opens the window or quits.
- **Start with Windows** (tray menu or Settings) opens just the widget at sign-in.
- **No setup.** Your name is taken from Windows. The team data folder is found automatically (below).
  The first-run dialog is gone.
- **Fewer inputs.** One line adds hours (project, hours, Add; date defaults to today, note optional).
  Typing a project name that is not in the list offers to create it. The timer needs only a project.
- **New interface and identity.** A top bar with three tabs (My time, Dashboard, Reports) replaces the
  sidebar; Settings is a dialog nobody needs to open. The app has its own name, mark and icon.
- Starting the app twice brings the running copy forward instead of opening a second one.

Earlier: revision 4 gave everyone one view, removed the Projects tab and imported dollar amounts;
revision 3 added the floating timer; revision 2 the navy, rounded-card look.

## How the team folder is found

1. A folder already in use (found earlier, or chosen in Settings) is kept.
2. Otherwise the app reads Dropbox's own `info.json` to learn where Dropbox is on the PC, and looks up to
   three levels down for a folder named **Discounted Engineering Data** (any letter case).
3. If it is not there yet, time is saved on that PC and a notice says so. Nothing is created inside
   Dropbox automatically, because a private copy would silently split the team's data. When the team
   folder appears, what was saved on the PC is moved into it at the next start (a project with the same
   name as a team project joins that project).

**One-off, for whoever runs the team folder:** create a folder called `Discounted Engineering Data`
somewhere in the team Dropbox, within three levels of the top, and share it with the engineers. To start
from the old sheet, use Settings > Import from Excel. Project data is not part of this repository.

## Build the .exe

1. Install Python 3.10 or newer on a Windows PC.
2. Double-click `build_exe.bat`. It creates a private build environment, installs the dependencies and
   produces `dist\Budget Tracker.exe`.
3. Give that one file to each person.

To run from source: `pip install -r requirements.txt`, then `run_app.bat` (or `python app.py`).
`python app.py --widget` opens only the widget.

## Screens

- **My time:** timer, one-line add, your entries for the week with edit and delete.
- **Dashboard:** discounted hours and dollars, projects over quote, top projects, trend, and splits by
  region, engineer and reason. Double-click a project for its entries, to edit it or delete it. New
  project (with all fields) is here too.
  The projects table shows the engineer, and its Columns button (or a right-click on a column heading)
  hides or shows columns, including SF ID, Approved by, Reason and Status. The choice is remembered per PC.
- **Reports:** week, month, financial year, custom range or all time; preview; export to PDF or Excel.
- **Settings:** name, theme, start with Windows, data folder; rate, financial-year start, regions and
  reason categories; Import from Excel.

## Rules the figures follow

- Quoted hours set: discounted hours = logged minus quoted (never below zero); over quote % =
  (logged - quoted) / quoted.
- No quote: every logged hour is discounted and no percentage is shown.
- Dollars = discounted hours x rate, with one exception: where a project has an imported amount, that
  figure replaces the rate for the project's imported hours. Hours logged afterwards are added at the rate.
- An imported amount with no imported hours is credited to the project's lead engineer; with hours, it is
  split between engineers in proportion to those hours.
- For a period, the quote is used up in date order (opening balances first). Only hours logged after the
  quote ran out count as discounted, in the period they were logged.
- Undated opening balances and imported amounts count in project totals and All time, not in any dated
  period, because the old sheet recorded no dates.
- Financial year starts 1 July (changeable). Weeks run Monday to Sunday.

## Data and limits

- Shared data is one small JSON file per project and per entry, so two people logging at once never write
  the same file. Deleting marks a record deleted; it does not remove the file.
- The app re-reads the folder every 30 seconds. Dropbox "conflicted copy" files and unreadable files are
  left out of totals and reported in a red banner.
- There is no access control. Anyone with the app and the folder can see and change everything.
- The widget is a desktop widget. It is not a Windows 11 Widgets-board widget: those must be shipped as a
  packaged (MSIX) app with a widget provider, which a single .exe cannot be.
- The widget has square corners and does not respond while a dialog box is open in the app.
- Settings, the running timer and the widget's position are stored per PC in
  `%LOCALAPPDATA%\DiscountedEngineeringTracker`.
- Import does not detect duplicates of existing projects; it warns and asks first.

## Tested and not tested

Tested (78 automated tests, run on Linux with Python 3.13 and PySide6 6.12): storage, calculations, the
automatic folder search and the move from local to team data (against a simulated Dropbox), the timer,
the widget as a separate window that survives closing the main window, Excel import, PDF and Excel
export, and smoke tests of every screen. The app was also launched end to end headless, including
widget-only start and the single-copy guard.

Not tested, because they need Windows: the .exe build, the tray icon, Start with Windows (registry),
reading the name from Windows, the widget staying on top of other programs, real Dropbox sync between
several PCs, and high-DPI scaling. Check these on a Windows PC before relying on the app.

Run the tests with `python -m pytest -q` (needs `pip install pytest`).
