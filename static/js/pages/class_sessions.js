/*
 * 課堂 page (ticket 11, #13): copy link.
 * Course actions are in static/js/course_actions.js; Class Session row actions in static/js/class_session_actions.js.
 */
(function () {
    'use strict';

    document.addEventListener('click', async (event) => {
        const copy = event.target.closest('[data-copy-url]');
        if (copy) {
            const ok = await copyToClipboard(copy.dataset.copyUrl);
            UI.toast(ok ? '已複製連結' : '複製失敗，請手動複製', ok ? 'ok' : 'error');
        }
    });
})();
