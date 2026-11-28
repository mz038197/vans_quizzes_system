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

// A Class Session with many Quiz Banks shows one summary line; this opens the details row under it.
document.addEventListener('click', (e) => {
    const toggle = e.target.closest('[data-banks-toggle]');
    if (!toggle) return;
    const details = document.getElementById(toggle.getAttribute('aria-controls'));
    if (!details) return;
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    details.hidden = !open;
});
