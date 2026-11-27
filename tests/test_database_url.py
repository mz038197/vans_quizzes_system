"""The database URL names its driver outright."""
import app as app_module


def test_database_url_names_the_psycopg2_driver():
    assert app_module.normalize_database_url('postgres://u:p@h/db') == 'postgresql+psycopg2://u:p@h/db'
    assert app_module.normalize_database_url('postgresql://u:p@h/db') == 'postgresql+psycopg2://u:p@h/db'
    assert app_module.normalize_database_url('postgresql+psycopg2://u@h/db') == 'postgresql+psycopg2://u@h/db'
    assert app_module.normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'
