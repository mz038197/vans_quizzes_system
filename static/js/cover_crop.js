/*
 * Folder cover cropper: the Teacher moves and resizes a 16:9 box on the picture to pick the part to keep.
 *
 *   const cropper = CoverCrop.create(pictureUrl, crop => { ... })   onChange gets each new crop
 *   container.append(cropper.node)
 *   cropper.crop()   { x, y, w, h }: parts (0 to 1) of the picture, or null until the picture loads
 *
 * The server keeps this part and fits it to 640×360 (folder_cover.make_cover). The box starts as the
 * biggest 16:9 part in the middle, the same as with no crop. Mouse or touch: drag the box to move it,
 * drag the corner to resize it. Keyboard: arrow keys move it, + and - resize it.
 * Styles: static/css/pages/quiz_banks.css (.crop-*).
 */
(function () {
    'use strict';

    const RATIO = 16 / 9;
    const MIN_PART = 0.15;   // the smallest box, as a part of the biggest box
    const STEP = 0.02;       // keyboard step, as a part of the picture
    const BIG_STEP = 0.1;    // with Shift

    function create(url, onChange) {
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
        const handle = document.createElement('span');
        handle.className = 'crop-handle';
        handle.setAttribute('aria-hidden', 'true');
        box.append(handle);
        stage.append(img, box);
        node.append(stage);
        box.hidden = true;

        // x, y, w are parts of the picture width/height; h follows from w so the box stays 16:9.
        let x = 0, y = 0, w = 1, heightPerWidth = 1, maxW = 1;
        let loaded = false;
        const h = () => w * heightPerWidth;
        const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

        function render() {
            box.style.left = `${x * 100}%`;
            box.style.top = `${y * 100}%`;
            box.style.width = `${w * 100}%`;
            box.style.height = `${h() * 100}%`;
            onChange(crop());
        }

        function place(newX, newY, newW) {
            w = clamp(newW, maxW * MIN_PART, maxW);
            x = clamp(newX, 0, 1 - w);
            y = clamp(newY, 0, 1 - h());
            render();
        }

        img.addEventListener('load', () => {
            // A 16:9 box that is w of the width is w × (width / height) × 9/16 of the height.
            heightPerWidth = (img.naturalWidth / img.naturalHeight) / RATIO;
            maxW = Math.min(1, 1 / heightPerWidth);
            loaded = true;
            box.hidden = false;
            place((1 - maxW) / 2, (1 - maxW * heightPerWidth) / 2, maxW);
        });
        img.src = url;

        function drag(event, move) {
            event.preventDefault();
            const rect = stage.getBoundingClientRect();
            const start = { px: event.clientX, py: event.clientY, x, y, w };
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
            if (event.target === handle) return;
            drag(event, (start, dx, dy) => place(start.x + dx, start.y + dy, start.w));
        });
        handle.addEventListener('pointerdown', (event) => {
            event.stopPropagation();
            // The top-left corner stays; the box follows the pointer across or down, whichever is further.
            drag(event, (start, dx, dy) => {
                const newW = Math.max(start.w + dx, start.w + dy / heightPerWidth);
                const fits = Math.min(1 - start.x, (1 - start.y) / heightPerWidth);
                place(start.x, start.y, Math.min(newW, fits));
            });
        });

        box.addEventListener('keydown', (event) => {
            const step = event.shiftKey ? BIG_STEP : STEP;
            const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
            if (moves[event.key]) {
                place(x + moves[event.key][0], y + moves[event.key][1], w);
            } else if (event.key === '+' || event.key === '=' || event.key === '-') {
                // Resize around the middle of the box.
                const newW = clamp(w + (event.key === '-' ? -step : step), maxW * MIN_PART, maxW);
                place(x + (w - newW) / 2, y + (w - newW) * heightPerWidth / 2, newW);
            } else {
                return;
            }
            event.preventDefault();
        });

        function crop() {
            return loaded ? { x, y, w, h: h() } : null;
        }

        return { node, crop };
    }

    window.CoverCrop = { create };
})();
