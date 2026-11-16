import json

from det import autostart, locate
from det.models import Entry, Project
from det.settings import Settings
from det.store import Store


def env_with_dropbox(tmp_path, business=True, personal=False):
    """A fake PC: %APPDATA%/Dropbox/info.json pointing at Dropbox folders under tmp_path."""
    appdata, local = tmp_path / 'AppData' / 'Roaming', tmp_path / 'AppData' / 'Local'
    (appdata / 'Dropbox').mkdir(parents=True)
    local.mkdir(parents=True)
    info = {}
    if business:
        (tmp_path / 'Team Dropbox').mkdir()
        info['business'] = {'path': str(tmp_path / 'Team Dropbox')}
    if personal:
        (tmp_path / 'Dropbox').mkdir()
        info['personal'] = {'path': str(tmp_path / 'Dropbox')}
    (appdata / 'Dropbox' / 'info.json').write_text(json.dumps(info))
    return {'APPDATA': str(appdata), 'LOCALAPPDATA': str(local)}


def settings_at(tmp_path):
    s = Settings(tmp_path / 'settings.json')
    s.load()
    return s


def test_dropbox_roots_business_first(tmp_path):
    env = env_with_dropbox(tmp_path, business=True, personal=True)
    assert [p.name for p in locate.dropbox_roots(env)] == ['Team Dropbox', 'Dropbox']
    assert locate.dropbox_roots({'APPDATA': str(tmp_path / 'nowhere')}) == []


def test_bad_info_file_is_ignored(tmp_path):
    env = env_with_dropbox(tmp_path)
    (tmp_path / 'AppData' / 'Roaming' / 'Dropbox' / 'info.json').write_text('{not json')
    assert locate.dropbox_roots(env) == []


def test_team_folder_is_found_without_asking(tmp_path):
    env = env_with_dropbox(tmp_path)
    target = tmp_path / 'Team Dropbox' / 'Engineering' / 'discounted engineering data'     # nested, different case
    target.mkdir(parents=True)
    (tmp_path / 'Team Dropbox' / '.dropbox.cache' / locate.DATA_FOLDER).mkdir(parents=True)  # must be skipped
    settings = settings_at(tmp_path)
    where = locate.resolve(settings, env)
    assert where.shared and where.path == target
    assert settings.get('shared_dir') == str(target) and settings.get('data_mode') == 'shared'


def test_too_deep_is_not_searched(tmp_path):
    env = env_with_dropbox(tmp_path)
    (tmp_path / 'Team Dropbox' / 'a' / 'b' / 'c' / 'd' / locate.DATA_FOLDER).mkdir(parents=True)
    assert locate.find_shared(locate.dropbox_roots(env)) is None


def test_without_team_folder_work_is_kept_on_this_pc(tmp_path):
    env = env_with_dropbox(tmp_path)
    settings = settings_at(tmp_path)
    where = locate.resolve(settings, env)
    assert not where.shared and where.path.is_dir() and where.path == locate.local_dir(env)
    assert settings.get('data_mode') == 'local'
    # nothing was created inside Dropbox: a private copy there would silently split the team's data
    assert list((tmp_path / 'Team Dropbox').iterdir()) == []


def test_local_work_moves_to_the_team_folder_when_it_appears(tmp_path):
    env = env_with_dropbox(tmp_path)
    settings = settings_at(tmp_path)
    local = Store(locate.resolve(settings, env).path)
    local.load()
    mine, same_name = Project(name='My new job'), Project(name='tower a')
    for p in (mine, same_name):
        local.save_project(p, new=True)
    local.save_entry(Entry(project_id=mine.id, engineer='Sam', date='2026-11-16', minutes=60), new=True)
    local.save_entry(Entry(project_id=same_name.id, engineer='Sam', date='2026-11-16', minutes=30), new=True)
    # the team folder syncs down later, already holding a project called "Tower A"
    team = Store(tmp_path / 'Team Dropbox' / locate.DATA_FOLDER)
    team.load()
    existing = Project(name='Tower A', quoted_hours=10)
    team.save_project(existing, new=True)
    where = locate.resolve(settings, env)
    assert where.shared and where.merged == 3            # one project and two entries moved across
    team.load()
    assert sorted(p.name for p in team.live_projects()) == ['My new job', 'Tower A']
    by_project = {e.project_id: e.minutes for e in team.live_entries()}
    assert by_project == {mine.id: 60, existing.id: 30}  # the same-name project's time joined the team's project
    assert locate.merge(locate.local_dir(env), where.path) == 0      # running it again adds nothing


def test_a_folder_chosen_by_hand_is_respected(tmp_path):
    env = env_with_dropbox(tmp_path)
    (tmp_path / 'Team Dropbox' / locate.DATA_FOLDER).mkdir()
    chosen = tmp_path / 'somewhere else'
    chosen.mkdir()
    settings = settings_at(tmp_path)
    settings.data.update(shared_dir=str(chosen), data_mode='shared')
    assert locate.resolve(settings, env).path == chosen
    settings.data.update(shared_dir=str(chosen), data_mode='')       # settings written by revision 4 and earlier
    assert locate.resolve(settings, env).path == chosen


def test_default_user_name_is_never_blank():
    assert locate.default_user_name().strip()


def test_autostart_command():
    assert autostart.launch_command(r'C:\Apps\Budget Tracker.exe', frozen=True) == r'"C:\Apps\Budget Tracker.exe" --widget'
    assert autostart.launch_command('/usr/bin/python3', script='/src/app.py', frozen=False) == \
        '"/usr/bin/python3" "/src/app.py" --widget'
    if not autostart.supported():
        assert autostart.is_enabled() is False and autostart.set_enabled(True) is False


def _data_set(root):
    """A data folder like the team's: one project, one entry, a config.json."""
    from det.models import Entry, Project
    s = Store(root)
    s.load()
    p = Project(name='Alpha')
    s.save_project(p, new=True)
    s.save_entry(Entry(project_id=p.id, engineer='Sam', date='2026-11-12', minutes=90), new=True)
    s.save_config()
    return p


def test_picking_the_projects_subfolder_means_its_parent(tmp_path):
    root = tmp_path / 'Data'
    _data_set(root)
    assert locate.data_root(root / 'Projects') == root
    assert locate.data_root(root / 'Entries') == root
    assert locate.data_root(root) == root
    lone = tmp_path / 'Projects'                      # a folder named Projects with no data set around it
    lone.mkdir()
    assert locate.data_root(lone) == lone


def test_saved_projects_subfolder_is_corrected_and_its_stray_files_ignored(tmp_path):
    """The reported fault: settings pointed at <data>/Projects, which had grown its own empty data set."""
    root = tmp_path / 'Data'
    _data_set(root)
    stray = Store(root / 'Projects')                  # what the old build created inside Projects
    stray.load()
    stray.save_config()
    settings = Settings(tmp_path / 'settings.json')
    settings.data.update(shared_dir=str(root / 'Projects'), data_mode='shared')
    location = locate.resolve(settings, env={})
    assert location.path == root and settings.get('shared_dir') == str(root)
    store = Store(location.path)
    store.load()
    assert len(store.projects) == 1 and len(store.entries) == 1 and store.warnings == []
