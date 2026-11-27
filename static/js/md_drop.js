/*
 * Markdown upload area (`label.drop` with a file input inside it).
 *
 *   MdDrop.attach('append-drop', 'append-md-file', file => { ... })
 *     The callback gets the chosen or dropped File. The area then shows the file name.
 *   MdDrop.setInfo('append-drop', '解析到 4 題')   one line of text under the file name
 *   MdDrop.clear('append-drop')                   back to the empty area
 *
 * Markup: see the drop area in templates/manage_quiz_bank.html (.drop-empty, .drop-file,
 * .drop-name, .drop-info). Styles: static/css/pages/quiz_bank.css.
 */
(function () {
    'use strict';

    function isMarkdown(file) {
        return /\.(md|markdown)$/i.test(file.name) || file.type === 'text/markdown';
    }

    function show(area, file) {
        area.classList.toggle('has', Boolean(file));
        area.querySelector('.drop-name').textContent = file ? file.name : '';
        area.querySelector('.drop-info').textContent = '';
    }

    function attach(areaId, inputId, onFile) {
        const area = document.getElementById(areaId);
        const input = document.getElementById(inputId);
        if (!area || !input) return;

        function take(file) {
            if (!file) return;
            if (!isMarkdown(file)) {
                UI.toast('請選擇 .md 檔案', 'warn');
                return;
            }
            show(area, file);
            onFile(file);
        }

        input.addEventListener('change', () => take(input.files && input.files[0]));
        ['dragenter', 'dragover'].forEach(name => area.addEventListener(name, event => {
            event.preventDefault();
            area.classList.add('is-over');
        }));
        ['dragleave', 'drop'].forEach(name => area.addEventListener(name, () => area.classList.remove('is-over')));
        area.addEventListener('drop', event => {
            event.preventDefault();
            const file = event.dataTransfer && event.dataTransfer.files[0];
            take(file);
        });
    }

    function setInfo(areaId, text) {
        const area = document.getElementById(areaId);
        if (area) area.querySelector('.drop-info').textContent = text;
    }

    function clear(areaId) {
        const area = document.getElementById(areaId);
        if (!area) return;
        const input = area.querySelector('input[type="file"]');
        if (input) input.value = '';
        show(area, null);
    }

    window.MdDrop = { attach, setInfo, clear };
})();
