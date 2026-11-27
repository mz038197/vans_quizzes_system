"""Teacher top navigation: the three areas 儀表板 / 題庫 / 課堂.

Templates get `teacher_nav` (the items to show) and `nav_area` (the active area).
A page can set its own area with `{% set nav_area = 'banks' %}` at the top of its template.

To add a page: put its endpoint in AREA_BY_ENDPOINT.
To add or move an area: edit NAV_ITEMS. An item links to the first endpoint in its list
that exists, so 題庫 links to the dashboard until the /quiz-banks page exists (ticket 06),
and 課堂 is hidden until the /class-sessions page exists (ticket 11).
"""

from flask import request, url_for

# (area, label, Font Awesome icon, endpoints to link to, in order of preference)
NAV_ITEMS = [
    ('dashboard', '儀表板', 'fa-chalkboard-teacher', ['teacher_dashboard']),
    ('banks', '題庫', 'fa-layer-group', ['quiz_banks', 'teacher_dashboard']),
    ('sessions', '課堂', 'fa-calendar-alt', ['class_sessions']),
]

AREA_BY_ENDPOINT = {
    'teacher_dashboard': 'dashboard',
    'quiz_banks': 'banks',
    'create_quiz_bank': 'banks',
    'manage_quiz_bank': 'banks',
    'view_submissions_page': 'banks',
    'view_submission_as_teacher': 'banks',
    'export_quiz_bank_pdf': 'banks',
    'class_sessions': 'sessions',
    'class_session_sheet': 'sessions',
    'course_sheet': 'sessions',
}


def register_page_nav(app):
    @app.context_processor
    def _inject_page_nav():
        items = []
        for area, label, icon, endpoints in NAV_ITEMS:
            endpoint = next((e for e in endpoints if e in app.view_functions), None)
            if endpoint is None:
                continue
            items.append({'area': area, 'label': label, 'icon': icon, 'url': url_for(endpoint)})
        return {
            'teacher_nav': items,
            'default_nav_area': AREA_BY_ENDPOINT.get(request.endpoint or ''),
        }
