"""Folder cover pictures: upload, show, remove. Driven through the HTTP routes."""

import io

from PIL import Image

from conftest import OWN_ORIGIN, TEACHER_ROUTER_ID, sign_in


def _picture(size=(1200, 900), fmt='JPEG', color=(200, 120, 40)):
    data = io.BytesIO()
    Image.new('RGB', size, color).save(data, fmt)
    return data.getvalue()


def _folder_id(client, name='高一資訊', color='amber'):
    response = client.post('/api/folders', json={'name': name, 'color': color})
    assert response.status_code == 201, response.get_json()
    return response.get_json()['folder']['id']


def _upload(client, folder_id, raw, filename='cover.jpg'):
    return client.put(f'/api/folders/{folder_id}/cover',
                      data={'cover': (io.BytesIO(raw), filename)},
                      content_type='multipart/form-data')


def _cover_url(client, folder_id):
    response = _upload(client, folder_id, _picture())
    assert response.status_code == 200, response.get_json()
    return response.get_json()['folder']['cover_url']


def test_uploaded_cover_comes_back_as_a_small_16_by_9_webp(auth_client):
    folder_id = _folder_id(auth_client)

    url = _cover_url(auth_client, folder_id)

    response = auth_client.get(url)
    assert response.status_code == 200
    assert response.mimetype == 'image/webp'
    picture = Image.open(io.BytesIO(response.data))
    assert picture.format == 'WEBP'
    assert picture.size == (640, 360)


def test_a_file_that_is_not_a_picture_is_refused_with_a_message(auth_client):
    folder_id = _folder_id(auth_client)

    response = _upload(auth_client, folder_id, b'%PDF-1.4 not a picture', 'notes.pdf')

    assert response.status_code == 400
    assert response.get_json()['error'] == '這個檔案不是可以讀的圖片'
    assert auth_client.get('/quiz-banks').status_code == 200


def test_a_picture_in_another_format_is_refused(auth_client):
    folder_id = _folder_id(auth_client)

    response = _upload(auth_client, folder_id, _picture(fmt='BMP'), 'cover.bmp')

    assert response.status_code == 400
    assert response.get_json()['error'] == '只接受 JPG、PNG、WebP 或 GIF 圖片'


def test_a_file_over_4_mb_is_refused_with_a_message(auth_client):
    folder_id = _folder_id(auth_client)

    response = _upload(auth_client, folder_id, b'x' * (4 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.get_json()['error'] == '檔案太大，最多 4 MB'


def test_another_teacher_can_not_see_or_change_the_cover(auth_client):
    folder_id = _folder_id(auth_client)
    url = _cover_url(auth_client, folder_id)

    sign_in(auth_client, TEACHER_ROUTER_ID + 1, name='別的老師')
    auth_client.environ_base['HTTP_ORIGIN'] = OWN_ORIGIN

    assert auth_client.get(url).status_code == 404
    assert _upload(auth_client, folder_id, _picture()).status_code == 404
    assert auth_client.delete(f'/api/folders/{folder_id}/cover').status_code == 404


def test_removed_cover_is_gone(auth_client):
    folder_id = _folder_id(auth_client)
    url = _cover_url(auth_client, folder_id)

    response = auth_client.delete(f'/api/folders/{folder_id}/cover')

    assert response.status_code == 200
    assert response.get_json()['folder']['cover_url'] is None
    assert auth_client.get(url).status_code == 404


def test_a_new_upload_gets_a_new_address(auth_client):
    folder_id = _folder_id(auth_client)

    first = _cover_url(auth_client, folder_id)
    second = _cover_url(auth_client, folder_id)

    assert first != second


def _html(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_folder_card_shows_the_cover_or_the_colour_block(auth_client):
    with_cover = _folder_id(auth_client, '有封面')
    _folder_id(auth_client, '沒封面')
    url = _cover_url(auth_client, with_cover)

    page = _html(auth_client, '/quiz-banks')

    card = page[page.index(f'data-folder="{with_cover}"'):]
    card = card[:card.index('</a>')]
    assert f"background-image:url('{url}')" in card.replace('&amp;', '&')
    plain = page[page.index('沒封面') - 600:page.index('沒封面')]
    assert 'background-image' not in plain[plain.rindex('data-folder='):]
    assert 'fcard-ph' in plain[plain.rindex('data-folder='):]


def test_folder_page_puts_the_name_on_the_cover(auth_client):
    folder_id = _folder_id(auth_client, '高一資訊')
    url = _cover_url(auth_client, folder_id)

    page = _html(auth_client, f'/quiz-banks?folder={folder_id}')

    hero = page[page.index('class="folder-hero'):]
    hero = hero[:hero.index('</h1>')]
    assert f"background-image:url('{url}')" in hero.replace('&amp;', '&')
    assert '高一資訊' in hero


def test_startup_adds_the_cover_columns_to_an_old_folder_table(client):
    from sqlalchemy import inspect, text

    from conftest import app_module

    with app_module.app.app_context():
        with app_module.db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE folder DROP COLUMN cover_image'))
            conn.execute(text('ALTER TABLE folder DROP COLUMN cover_updated_at'))

        app_module.ensure_schema_updates()
        app_module.ensure_schema_updates()

        columns = {c['name'] for c in inspect(app_module.db.engine).get_columns('folder')}
        assert {'cover_image', 'cover_updated_at'} <= columns
