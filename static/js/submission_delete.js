/*
 * Delete several Submissions at once (POST /api/submissions/delete). Used by the Quiz Bank grades
 * page (rows = Submissions, body {ids}) and the 課堂總表 (rows = students, body {class_session_id, students}).
 *
 *   const bar = SubmissionDelete.bar({ onDelete, onClear })    the bottom action bar (_bulk_bar.html)
 *   bar.show(count, unit)                                     hidden when count is 0
 *   SubmissionDelete.syncSelectAll(box, selected, total)      checked, unchecked or partly checked
 *   await SubmissionDelete.run(body, { count, names, unit, scope })   asks, sends; the result or null
 *
 * The dialog names the students, trimmed and each once (the first 5, then 「…等 N 位」).
 * For 2 or more, the teacher types the count.
 */
(function () {
    'use strict';

    const SHOWN_NAMES = 5;

    function nameList(names) {
        const unique = [...new Set(names.map(name => (name || '').trim()))];
        const shown = unique.slice(0, SHOWN_NAMES).join('、');
        return unique.length > SHOWN_NAMES ? `${shown}…等 ${unique.length} 位` : shown;
    }

    function bar({ onDelete, onClear }) {
        const box = document.getElementById('bulk-bar');
        box.querySelector('[data-bulk-delete]').addEventListener('click', onDelete);
        box.querySelector('[data-bulk-clear]').addEventListener('click', onClear);
        return {
            show(count, unit) {
                box.querySelector('[data-bulk-count]').textContent = `已選 ${count} ${unit}`;
                box.querySelector('[data-bulk-delete]').textContent = `刪除 ${count} ${unit}`;
                box.hidden = count === 0;
            },
        };
    }

    function syncSelectAll(box, selected, total) {
        box.checked = selected > 0 && selected === total;
        box.indeterminate = selected > 0 && selected < total;
    }

    async function run(body, { count, names, unit, scope }) {
        const ok = await UI.ask(
            `會永久刪除 ${nameList(names)} ${scope}，學生的成績單連結也會打不開。這個動作無法復原。`,
            { title: `刪除 ${count} ${unit}？`, danger: true, okText: '刪除',
              matchText: count >= 2 ? String(count) : undefined });
        if (!ok) return null;
        try {
            const response = await fetch('/api/submissions/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const result = await response.json();
            if (!response.ok) {
                UI.toast(result.error || '刪除失敗，請稍後再試', 'error');
                return null;
            }
            return result;
        } catch (error) {
            UI.toast('網路錯誤，請檢查連線', 'error');
            return null;
        }
    }

    window.SubmissionDelete = { bar, syncSelectAll, run };
})();
