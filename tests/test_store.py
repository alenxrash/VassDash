import pytest

from det.models import Entry, Project
from det.store import Store, validate_entry


def make(tmp_path):
    store = Store(tmp_path / 'shared')
    store.load()
    return store


def test_round_trip(tmp_path):
    store = make(tmp_path)
    p = Project(name='Tower A', region='QLD', quoted_hours=10.5)
    store.save_project(p, new=True)
    e = Entry(project_id=p.id, engineer='Sam', date='2026-11-12', minutes=150)
    store.save_entry(e, new=True)
    again = Store(tmp_path / 'shared')
    again.load()
    assert again.projects[p.id].name == 'Tower A'
    assert again.projects[p.id].quoted_hours == 10.5
    assert again.entries[e.id].minutes == 150
    assert again.entries[e.id].hours == 2.5
    assert again.warnings == []


def test_new_id_collision(tmp_path):
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    with pytest.raises(FileExistsError):
        store.save_project(p, new=True)


def test_soft_delete(tmp_path):
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    e = Entry(project_id=p.id, engineer='Sam', date='2026-11-12', minutes=60)
    store.save_entry(e, new=True)
    store.delete_entry(e.id)
    store.delete_project(p.id)
    assert store.live_entries() == [] and store.live_projects() == []
    assert (tmp_path / 'shared' / 'Entries' / f'{e.id}.json').exists()
    again = Store(tmp_path / 'shared')
    again.load()
    assert again.entries[e.id].deleted and again.live_entries() == []


def test_bad_files_skipped_and_counted(tmp_path):
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    folder = tmp_path / 'shared' / 'Projects'
    (folder / f"{p.id} (Sam's conflicted copy 2026-11-14).json").write_text('{}')
    (folder / 'broken.json').write_text('{bad')
    store.load()
    assert len(store.live_projects()) == 1
    assert len(store.warnings) == 2


def test_no_temp_files_left(tmp_path):
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    p.name = 'B'
    store.save_project(p)
    store.save_config()
    leftovers = [f for f in (tmp_path / 'shared').rglob('*') if f.is_file() and f.suffix != '.json']
    assert leftovers == []


def test_signature_changes(tmp_path):
    store = make(tmp_path)
    before = store.signature()
    store.save_project(Project(name='A'), new=True)
    assert store.signature() != before


@pytest.mark.parametrize('minutes', [0, 1441, -5])
def test_minutes_range(tmp_path, minutes):
    store = make(tmp_path)
    with pytest.raises(ValueError):
        validate_entry(Entry(project_id='x', engineer='Sam', minutes=minutes))


def test_entry_needs_project():
    with pytest.raises(ValueError):
        validate_entry(Entry(project_id='', engineer='Sam', minutes=60))


def test_config_defaults_and_persist(tmp_path):
    store = make(tmp_path)
    assert store.config.rate == 220.0 and store.config.fy_start_month == 7
    store.config.rate = 240.0
    store.save_config()
    again = Store(tmp_path / 'shared')
    again.load()
    assert again.config.rate == 240.0


def test_projects_sort_naturally(tmp_path):
    store = make(tmp_path)
    for name in ('Project 10', 'Project 2', 'alpha', 'Project (row 19)'):
        store.save_project(Project(name=name), new=True)
    assert [p.name for p in store.live_projects()] == ['alpha', 'Project 2', 'Project 10', 'Project (row 19)']


def test_entry_with_bad_date_is_skipped(tmp_path):
    import json
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    e = Entry(project_id=p.id, engineer='Sam', date='2026-11-12', minutes=60)
    store.save_entry(e, new=True)
    path = tmp_path / 'shared' / 'Entries' / f'{e.id}.json'
    data = json.loads(path.read_text())
    data['date'] = '12/11/2026'
    path.write_text(json.dumps(data))
    store.load()
    assert store.live_entries() == [] and len(store.warnings) == 1


def test_engineer_list_merges_case_variants(tmp_path):
    store = make(tmp_path)
    p = Project(name='A')
    store.save_project(p, new=True)
    for who in ('NATHAN', 'NAthan', 'Cody'):
        store.save_entry(Entry(project_id=p.id, engineer=who, date='2026-11-12', minutes=60), new=True)
    assert store.engineers() == ['Cody', 'Nathan']
