from unittest.mock import patch, MagicMock
from jobs.common.db import DBConnection

FAKE_CONF = {
    'mysql_host': 'localhost',
    'mysql_user': 'root',
    'mysql_password': '',
    'mysql_database': 'test',
}

@patch('jobs.common.db.pymysql.connect')
def test_ensure_connected_creates_connection(mock_connect):
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn
    db = DBConnection(FAKE_CONF)
    conn = db.ensure_connected()
    assert conn is mock_conn
    mock_connect.assert_called_once()

@patch('jobs.common.db.pymysql.connect')
def test_fetch_rows(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [{'id': 1}]
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.open = True
    mock_connect.return_value = mock_conn
    db = DBConnection(FAKE_CONF)
    rows = db.fetch_rows("SELECT 1")
    assert rows == [{'id': 1}]
