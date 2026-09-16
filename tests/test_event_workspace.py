from pathlib import Path
from unittest.mock import patch
import pytest
from database.db import init_db, get_conn
from database.repository import create_event, delete_all_events, get_events
from services.event_workspace import create_workspace, workspace_path, save_output, cleanup_workspace
from services.heat_outputs import generate_outputs, current_outputs


def event(db):
    init_db(db)
    return create_event(db, 'Meet', 'GN', '2026-09-01', 'SCM', 6)


def test_creation_and_separate_outputs(tmp_path):
    db = tmp_path / 'events.sqlite'
    first, second = event(db), event(db)
    folder = create_workspace(db, first)
    assert {p.name for p in folder.iterdir()} == {'uploads', 'outputs', 'temp'}
    assert list((folder / 'uploads').iterdir()) == []
    one = save_output(db, first, 'results.xml', b'first')
    two = save_output(db, second, 'results.xml', b'second')
    assert one == tmp_path / 'runtime' / f'event_{first}' / 'outputs/results.xml'
    assert one.read_bytes() == b'first' and two.read_bytes() == b'second'


@pytest.mark.parametrize('cleanup', [False, True])
def test_reset_preserves_unrelated_and_permanent_files(tmp_path, cleanup):
    db = tmp_path / 'events.sqlite'
    eid = event(db)
    output = save_output(db, eid, 'test.pdf', b'event')
    unrelated = save_output(db, 999, 'test.pdf', b'other')
    permanent = []
    for name in ('season_results.sqlite', 'fixtures/reference.json', 'templates/template.xlsx', 'examples/sample.pdf'):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'permanent')
        permanent.append(path)
    delete_all_events(db, delete_event_files=cleanup)
    assert not get_events(db)
    assert output.exists() is not cleanup
    assert unrelated.read_bytes() == b'other'
    assert all(path.read_bytes() == b'permanent' for path in permanent)
    assert current_outputs(db, eid) == {}


def test_cleanup_one_event_and_missing_workspace(tmp_path):
    db = tmp_path / 'events.sqlite'
    one, two = event(db), event(db)
    save_output(db, one, 'out.json', b'one')
    other = save_output(db, two, 'out.json', b'two')
    cleanup_workspace(db, one)
    cleanup_workspace(db, one)
    assert other.read_bytes() == b'two'
    delete_all_events(db, delete_event_files=True)
    assert not get_events(db)


@pytest.mark.parametrize('eid', ['../data', '../../', 0, -1, True, '1', 1.2])
def test_cleanup_rejects_invalid_ids(tmp_path, eid):
    with pytest.raises(ValueError):
        cleanup_workspace(tmp_path / 'events.sqlite', eid)


def test_cleanup_rejects_resolved_escape(tmp_path):
    db = tmp_path / 'events.sqlite'
    event(db)
    original = Path.resolve
    target = tmp_path / 'runtime/event_1'
    def redirected(path, *args, **kwargs):
        return tmp_path if path == target else original(path, *args, **kwargs)
    with patch.object(Path, 'resolve', redirected), pytest.raises(ValueError):
        cleanup_workspace(db, 1)


@pytest.mark.parametrize('filename', ['../reference.json', 'sub/file', 'C:\\history.sqlite', '..'])
def test_output_rejects_escape(tmp_path, filename):
    with pytest.raises(ValueError):
        save_output(tmp_path / 'events.sqlite', 1, filename, b'bad')


def test_package_disk_storage_and_invalidation(tmp_path):
    db = tmp_path / 'events.sqlite'
    eid = event(db)
    with get_conn(db) as conn:
        conn.execute('UPDATE events SET approved_revision=heat_revision WHERE id=?', (eid,))
    package = {'meet_program.json': ('application/json', b'{}')}
    with patch('services.heat_outputs.build_package', return_value=package):
        assert generate_outputs(db, eid, {}) == package
    assert current_outputs(db, eid) == package
    path = workspace_path(db, eid) / 'outputs/meet_program.json'
    assert path.read_bytes() == b'{}'
    path.write_bytes(b'incomplete')
    assert current_outputs(db, eid) == {}
    path.unlink()
    assert current_outputs(db, eid) == {}
    cleanup_workspace(db, eid)
    with get_conn(db) as conn:
        assert not conn.execute('SELECT * FROM event_outputs').fetchall()
        assert conn.execute('SELECT exports_revision FROM events').fetchone()[0] is None


@pytest.mark.parametrize('cleanup', [False, True])
def test_reset_ui(tmp_path, monkeypatch, cleanup):
    from test_season_results_ui import app_test
    app = app_test(tmp_path, monkeypatch)
    db = tmp_path / 'data/biathlon_events.sqlite'
    eid = event(db)
    output = save_output(db, eid, 'result.pdf', b'event')
    app.session_state['timedrops_json'] = 'old download'
    app.run()
    app.button(key='reset_sessions').click().run()
    checkbox = next(c for c in app.checkbox if c.label == 'Also delete event files')
    assert checkbox.value is False
    assert checkbox.proto.help == 'Deletes files uploaded or generated for the events being cleared. Historical season results are not affected.'
    checkbox.set_value(cleanup).run()
    app.button(key='confirm_reset_sessions_button').click().run()
    assert not app.exception
    assert output.exists() is not cleanup
    assert not get_events(db)
    assert 'timedrops_json' not in app.session_state
