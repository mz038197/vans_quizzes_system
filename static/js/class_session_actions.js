/*
 * Class Session row actions (ticket 11, #13). Used by the 課堂 page, the 課堂 tab of the Quiz Bank page,
 * the 課堂總表, and the Class Session cards on the 儀表板 (編輯課堂 only).
 *
 *   <button data-cs-action="end|start-now|extend|reopen" data-id="<Class Session id>">   POST /api/class-sessions/<id>/<action>
 *   <button data-cs-edit="<id>">     opens the shared dialog in edit mode (ClassSessionDialog.open({ session }))
 *   <button data-cs-delete="<id>">   asks first; with Submissions the Class Session name must be typed
 *
 * After a change the page reloads and shows the server message as a toast.
 */
(function () {
    'use strict';

    async function call(url, method, body) {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        return { ok: response.ok, status: response.status, data };
    }

    const sessionUrl = (id) => `/api/class-sessions/${encodeURIComponent(id)}`;

    async function loadSession(id) {
        const result = await call(sessionUrl(id), 'GET');
        if (!result.ok) { UI.toast(result.data.error || '讀取課堂失敗', 'error'); return null; }
        return result.data;
    }

    async function act(button) {
        const action = button.dataset.csAction;
        button.disabled = true;
        try {
            const result = await call(`${sessionUrl(button.dataset.id)}/${action}`, 'POST', action === 'extend' ? { minutes: 10 } : {});
            if (!result.ok) { UI.toast(result.data.error || '操作失敗，請稍後再試', 'error'); return; }
            UI.flash(result.data.message || '已更新課堂', 'ok');
            location.reload();
        } catch (e) {
            UI.toast('網路錯誤，請稍後再試', 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function edit(id) {
        const session = await loadSession(id);
        if (!session) return;
        const saved = await ClassSessionDialog.open({ session });
        if (!saved) return;
        UI.flash(`已更新課堂「${saved.name}」`, 'ok');
        location.reload();
    }

    async function remove(id) {
        const session = await loadSession(id);
        if (!session) return;
        const n = session.n_subs;
        const ok = await UI.ask(
            n ? `會永久刪除這堂課和它的 ${n} 份作答紀錄，學生的成績單連結也會打不開。這個動作無法復原。`
              : '這堂課還沒有人作答。刪除後，它的連結和 QR code 會失效。',
            { title: `刪除課堂「${session.name}」？`, danger: true, okText: '刪除課堂', matchText: n ? session.name : undefined });
        if (!ok) return;
        const result = await call(sessionUrl(id), 'DELETE', { confirm: true });
        if (!result.ok) { UI.toast(result.data.error || '刪除失敗，請稍後再試', 'error'); return; }
        UI.flash(result.data.message || '已刪除課堂', 'ok');
        location.reload();
    }

    document.addEventListener('click', (event) => {
        const action = event.target.closest('[data-cs-action]');
        if (action) { event.preventDefault(); act(action); return; }
        const editButton = event.target.closest('[data-cs-edit]');
        if (editButton) { event.preventDefault(); edit(editButton.dataset.csEdit); return; }
        const deleteButton = event.target.closest('[data-cs-delete]');
        if (deleteButton) { event.preventDefault(); remove(deleteButton.dataset.csDelete); }
    });

    window.ClassSessionActions = { call, edit, remove };
})();
