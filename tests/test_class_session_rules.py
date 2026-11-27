"""Plain rules in class_session_rules.py that the routes share (review fixes 10-12)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import class_session_rules as rules

NOW = datetime(2026, 11, 27, 4, 0)  # 12:00 UTC+8


def _course(ended_at=None, ends_at=None):
    return SimpleNamespace(ended_at=ended_at, ends_at=ends_at)


def _session(starts_in, ends_in, course=None):
    return SimpleNamespace(starts_at=NOW + timedelta(minutes=starts_in), ends_at=NOW + timedelta(minutes=ends_in),
                           course=course or _course())


def test_course_end_text_uses_the_utc8_day():
    # 23:59 UTC+8 on 12/31 is 15:59 UTC
    assert rules.course_end_text(_course(ends_at=datetime(2026, 12, 31, 15, 59)), NOW) == '到 12/31 23:59'
    # 17:00 UTC on 11/26 is 01:00 on 11/27 in UTC+8
    assert rules.course_end_text(_course(ended_at=datetime(2026, 11, 26, 17, 0)), NOW) == '已在 11/27 結束'
    assert rules.course_end_text(_course(ends_at=datetime(2026, 11, 20, 15, 59)), NOW) == '已在 11/20 結束'
    assert rules.course_end_text(_course(), NOW) == '沒有結束日期'


def test_parse_course_end_is_23_59_utc8_and_refuses_a_past_day():
    assert rules.parse_course_end('2026-12-31', NOW) == (datetime(2026, 12, 31, 15, 59), None)
    assert rules.parse_course_end('', NOW) == (None, None)
    assert rules.parse_course_end('2026-11-01', NOW)[1]
    assert rules.parse_course_end('31/12/2026', NOW)[1]


def test_list_order_is_live_then_soon_by_start_then_done_by_latest_end():
    rows = {
        'live': _session(-10, 30), 'soon_late': _session(120, 180), 'soon': _session(60, 90),
        'done_old': _session(-300, -240), 'done_new': _session(-120, -60),
    }
    ordered = sorted(rows, key=lambda k: rules.list_order(rows[k], rules.status(rows[k], NOW)))
    assert ordered == ['live', 'soon', 'soon_late', 'done_new', 'done_old']


def test_has_started():
    assert rules.has_started(_session(0, 10), NOW)
    assert not rules.has_started(_session(1, 10), NOW)
