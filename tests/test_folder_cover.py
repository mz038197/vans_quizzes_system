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


def test_after_removal_the_card_shows_the_colour_block_again(auth_client):
    folder_id = _folder_id(auth_client, '換回顏色')
    _cover_url(auth_client, folder_id)

    auth_client.delete(f'/api/folders/{folder_id}/cover')

    page = _html(auth_client, '/quiz-banks')
    card = page[page.index(f'data-folder="{folder_id}"'):]
    card = card[:card.index('</a>')]
    assert 'background-image' not in card
    assert 'fcard-ph' in card


# ---- The Teacher picks the part of the picture to keep (form field "crop") ----

QUARTERS = {'top-left': ((0, 0), (220, 30, 30)), 'top-right': ((1, 0), (30, 200, 30)),
            'bottom-left': ((0, 1), (30, 30, 220)), 'bottom-right': ((1, 1), (230, 200, 20))}


def _colour(quarter):
    return QUARTERS[quarter][1]


def _four_colour_picture(fmt='PNG', exif=None):
    """1600×900, each quarter one colour: a 16:9 quarter is 800×450."""
    picture = Image.new('RGB', (1600, 900))
    for (column, row), colour in QUARTERS.values():
        picture.paste(colour, (column * 800, row * 450, column * 800 + 800, row * 450 + 450))
    data = io.BytesIO()
    picture.save(data, fmt, **({'exif': exif} if exif else {}))
    return data.getvalue()


def _upload_with_crop(client, folder_id, crop=None, raw=None):
    data = {'cover': (io.BytesIO(raw or _four_colour_picture()), 'cover.png')}
    if crop is not None:
        data['crop'] = crop
    return client.put(f'/api/folders/{folder_id}/cover', data=data, content_type='multipart/form-data')


def _cover(client, response):
    assert response.status_code == 200, response.get_json()
    picture = Image.open(io.BytesIO(client.get(response.get_json()['folder']['cover_url']).data)).convert('RGB')
    assert picture.size == (640, 360)
    return picture


def _near(colour, expected):
    return all(abs(a - b) <= 12 for a, b in zip(colour, expected))


def test_the_cover_keeps_the_part_the_teacher_picked(auth_client):
    folder_id = _folder_id(auth_client)

    top_left = _cover(auth_client, _upload_with_crop(auth_client, folder_id, '0,0,0.5,0.5'))
    bottom_right = _cover(auth_client, _upload_with_crop(auth_client, folder_id, '0.5,0.5,0.5,0.5'))

    assert _near(top_left.getpixel((320, 180)), _colour('top-left'))
    assert _near(bottom_right.getpixel((320, 180)), _colour('bottom-right'))


def test_without_a_crop_the_cover_is_the_middle_of_the_picture(auth_client):
    cover = _cover(auth_client, _upload_with_crop(auth_client, _folder_id(auth_client)))

    assert _near(cover.getpixel((80, 45)), _colour('top-left'))
    assert _near(cover.getpixel((560, 315)), _colour('bottom-right'))


def test_the_crop_is_of_the_picture_turned_upright_as_the_browser_shows_it(auth_client):
    exif = Image.Exif()
    exif[0x0112] = 6  # the camera was turned: show the picture turned 90° clockwise (900×1600)
    raw = _four_colour_picture('JPEG', exif)

    # The top-left 16:9 part of the upright picture: 450×253 of 900×1600.
    cover = _cover(auth_client, _upload_with_crop(auth_client, _folder_id(auth_client), '0,0,0.5,0.158', raw))

    assert _near(cover.getpixel((320, 180)), _colour('bottom-left'))


def test_a_small_crop_of_a_big_photo_keeps_its_detail(auth_client):
    """Fine stripes 2 px wide on a 6000×4000 photo. A big JPEG is read at a smaller size to save memory;
    for a small crop that size must still be big enough, or the stripes become one grey."""
    picture = Image.new('L', (6000, 4000), 255)
    for left in range(2400, 3900, 4):  # only in the crop, so the file stays under 4 MB
        picture.paste(0, (left, 1600, left + 2, 2444))
    data = io.BytesIO()
    picture.save(data, 'JPEG', quality=95)

    # A quarter of the width, 16:9: 1500×844 of 6000×4000.
    cover = _cover(auth_client, _upload_with_crop(auth_client, _folder_id(auth_client), '0.4,0.4,0.25,0.2109',
                                                  data.getvalue()))

    row = [cover.getpixel((x, 180))[0] for x in range(200, 440)]
    assert max(row) - min(row) > 50


def test_a_crop_outside_the_picture_or_not_numbers_is_refused(auth_client):
    folder_id = _folder_id(auth_client)
    for crop in ('0.8,0,0.5,0.5', '0,0,0,0', '-0.1,0,0.5,0.5', 'abc', '0,0,0.5', 'nan,0,0.5,0.5'):
        response = _upload_with_crop(auth_client, folder_id, crop)
        assert response.status_code == 400, crop
        assert response.get_json()['error'] == '裁切範圍不對，請重新選取', crop
    assert auth_client.get('/quiz-banks').status_code == 200


def test_quiz_banks_page_loads_the_cover_cropper(auth_client):
    assert '/static/js/cover_crop.js' in _html(auth_client, '/quiz-banks')
