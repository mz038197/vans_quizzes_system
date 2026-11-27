"""Issue #22: an old database got quiz_bank.folder_id through ALTER TABLE, without the index that
the model declares. Startup adds the index; running startup again changes nothing."""
from sqlalchemy import inspect, text

from conftest import app_module


def _folder_id_indexed():
    indexes = inspect(app_module.db.engine).get_indexes('quiz_bank')
    return any(index['column_names'] == ['folder_id'] for index in indexes)


def test_startup_adds_the_missing_folder_index_and_can_run_again(client):
    with app_module.app.app_context():
        with app_module.db.engine.begin() as conn:
            conn.execute(text('DROP INDEX IF EXISTS ix_quiz_bank_folder_id'))
        assert not _folder_id_indexed()

        app_module.ensure_schema_updates()
        assert _folder_id_indexed()

        app_module.ensure_schema_updates()
        assert _folder_id_indexed()
