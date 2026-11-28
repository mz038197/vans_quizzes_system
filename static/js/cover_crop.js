/*
 * Folder cover cropper: the Teacher moves and resizes a 16:9 box on the picture to pick the part to keep.
 *
 *   const cropper = CoverCrop.create(pictureUrl, { onChange, onError })
 *   container.append(cropper.node)
 *   cropper.crop()        { x, y, width, height }: parts (0 to 1) of the picture; null until it loads
 *   cropper.formValue()   the "crop" form field for PUT /api/folders/<id>/cover ('' until it loads)
 *   CoverCrop.previewStyle(crop)   background-size and -position that show only the crop in a 16:9 box
 *
 * onChange gets each new crop. onError runs when the browser cannot show the picture.
 * The server keeps the crop and fits it to 640×360 (folder_cover.make_cover). The box starts as the
 * biggest 16:9 part in the middle, the same as with no crop. Mouse or touch: drag the box to move it,
 * drag a corner to resize it (the opposite corner stays). Keyboard: arrow keys move it (Shift: bigger
 * steps), + and - resize it around its middle.
 * Styles: static/css/pages/quiz_banks.css (.crop-*).
 */
(function () {
    'use strict';

    const RATIO = 16 / 9;
    const MIN_PART = 0.25;   // the smallest box, as a part of the biggest box (the corners need room)
    const STEP = 0.02;       // keyboard step, as a part of the picture
    const BIG_STEP = 0.1;    // arrow keys with Shift
    const CORNERS = ['nw', 'ne', 'sw', 'se'];

    function create(url, { onChange, onError }) {
        const node = document.createElement('div');
        node.className = 'crop-wrap';
        const stage = document.createElement('div');
        stage.className = 'crop-stage';
        const img = document.createElement('img');
        img.alt = '';
        img.draggable = false;
        const box = document.createElement('div');
        box.className = 'crop-box';
        box.tabIndex = 0;
        box.setAttribute('role', 'group');
        box.setAttribute('aria-label', '封面範圍：方向鍵移動，+ 和 - 改大小');
        box.hidden = true;
        CORNERS.forEach((corner) => {
            const handle = document.createElement('span');
            handle.className = 'crop-handle';
            handle.dataset.corner = corner;
            handle.setAttribute('aria-hidden', 'true');
            box.append(handle);
        });
        stage.append(img, box);
        node.append(stage);

        // left, top, width: parts of the picture width/height. The height follows, so the box stays 16:9.
        let left = 0, top = 0, width = 1;
        let heightPerWidth = 1;  // a box that is 1 picture width wide is this many picture heights high
        let maxWidth = 1;
        let loaded = false;
        const height = () => width * heightPerWidth;
        const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

        function render() {
            box.style.left = `${left * 100}%`;
            box.style.top = `${top * 100}%`;
            box.style.width = `${width * 100}%`;
            box.style.height = `${height() * 100}%`;
            onChange(crop());
        }

        function place(newLeft, newTop, newWidth) {
            width = clamp(newWidth, maxWidth * MIN_PART, maxWidth);
            left = clamp(newLeft, 0, 1 - width);
            top = clamp(newTop, 0, 1 - height());
            render();
        }

        img.addEventListener('load', () => {
            heightPerWidth = (img.naturalWidth / img.naturalHeight) / RATIO;
            maxWidth = Math.min(1, 1 / heightPerWidth);
            loaded = true;
            box.hidden = false;
            place((1 - maxWidth) / 2, (1 - maxWidth * heightPerWidth) / 2, maxWidth);
        });
        img.addEventListener('error', () => onError());
        img.src = url;

        /* Follow one pointer until it is released. move(start, dx, dy) gets the distance as parts of the picture. */
        function drag(event, move) {
            event.preventDefault();
            const rect = stage.getBoundingClientRect();
            const start = { px: event.clientX, py: event.clientY, left, top, width, height: height() };
            const target = event.currentTarget;
            target.setPointerCapture(event.pointerId);
            const onMove = (e) => move(start, (e.clientX - start.px) / rect.width, (e.clientY - start.py) / rect.height);
            const onUp = () => {
                target.removeEventListener('pointermove', onMove);
                target.removeEventListener('pointerup', onUp);
                target.removeEventListener('pointercancel', onUp);
            };
            target.addEventListener('pointermove', onMove);
            target.addEventListener('pointerup', onUp);
            target.addEventListener('pointercancel', onUp);
        }

        box.addEventListener('pointerdown', (event) => {
            if (event.target !== box) return;
            drag(event, (start, dx, dy) => place(start.left + dx, start.top + dy, start.width));
        });
        box.querySelectorAll('.crop-handle').forEach((handle) => {
            const east = handle.dataset.corner.includes('e');
            const south = handle.dataset.corner.includes('s');
            handle.addEventListener('pointerdown', (event) => {
                // The opposite corner stays. The box follows the pointer across or down, whichever is further.
                drag(event, (start, dx, dy) => {
                    const across = start.width + (east ? dx : -dx);
                    const down = start.width + (south ? dy : -dy) / heightPerWidth;
                    const room = Math.min(east ? 1 - start.left : start.left + start.width,
                                          (south ? 1 - start.top : start.top + start.height) / heightPerWidth);
                    const newWidth = clamp(Math.max(across, down), maxWidth * MIN_PART, Math.min(maxWidth, room));
                    place(east ? start.left : start.left + start.width - newWidth,
                          south ? start.top : start.top + start.height - newWidth * heightPerWidth,
                          newWidth);
                });
            });
        });

        box.addEventListener('keydown', (event) => {
            const step = event.shiftKey ? BIG_STEP : STEP;
            const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
            const resize = { '+': STEP, '=': STEP, '-': -STEP }[event.key];
            if (moves[event.key]) {
                place(left + moves[event.key][0], top + moves[event.key][1], width);
            } else if (resize) {
                const newWidth = clamp(width + resize, maxWidth * MIN_PART, maxWidth);
                place(left + (width - newWidth) / 2, top + (width - newWidth) * heightPerWidth / 2, newWidth);
            } else {
                return;
            }
            event.preventDefault();
        });

        function crop() {
            return loaded ? { x: left, y: top, width, height: height() } : null;
        }

        function formValue() {
            const c = crop();
            return c ? [c.x, c.y, c.width, c.height].map((n) => n.toFixed(5)).join(',') : '';
        }

        return { node, crop, formValue };
    }

    /* The picture is 1/width of the preview wide; a position of p% puts the picture's p% point at the box's p% point. */
    function previewStyle(crop) {
        const percentAt = (start, size) => (size < 1 ? (start / (1 - size)) * 100 : 0);
        return {
            backgroundSize: `${100 / crop.width}% auto`,
            backgroundPosition: `${percentAt(crop.x, crop.width)}% ${percentAt(crop.y, crop.height)}%`,
        };
    }

    window.CoverCrop = { create, previewStyle };
})();
