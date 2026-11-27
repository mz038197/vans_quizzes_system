/*
 * Course actions (ticket 11, #13; review fix 3). Used by the 課堂 page and the 課程總表.
 *
 *   <section data-course="<id>" data-name data-ends-on data-active data-sessions data-subs>   the Course the buttons act on
 *     <button data-course-action="edit|end|reopen|delete">
 *   <button data-course-new>   新課程
 *
 * Needs static/js/class_session_actions.js (ClassSessionActions.call). After a change the page reloads
 * and shows the server message as a toast. window.CourseActions.dialog(course | null) opens 新課程 / 編輯課程.
 */
(function () {
    'use strict';

    const call = (url, method, body) => ClassSessionActions.call(url, method, body);
    const done = (message) => { UI.flash(message, 'ok'); location.reload(); };

    function todayUtc8() {
        return new Date(Date.now() + 8 * 3600e3).toISOString().slice(0, 10);
    }

    /* 新課程 / 編輯課程: name and an optional end date (23:59 UTC+8 that day). Resolves when saved. */
    function courseDialog(course) {
        const box = document.createElement('div');
        box.className = 'crs-dlg stack';
        box.innerHTML = `
            <div class="fld"><label for="crs-name">課程名稱</label>
                <input class="inp" id="crs-name" maxlength="200" placeholder="例如：高一 3 班 · 115 上" autocomplete="off"></div>
            <div class="fld"><label for="crs-end">結束日期 <span class="muted small">· 可以不填</span></label>
                <input class="inp" id="crs-end" type="date" min="${todayUtc8()}">
                <span class="help">這天 23:59 以後，課程自動結束，底下所有課堂一起結束。不填的話，課程會一直開著，直到你按「結束課程」。</span></div>
            <p class="err danger-text small" id="crs-err" role="alert"></p>`;
        const name = box.querySelector('#crs-name'), end = box.querySelector('#crs-end'), err = box.querySelector('#crs-err');
        name.value = course ? course.name : '';
        end.value = course ? course.endsOn : '';
        async function save() {
            err.textContent = '';
            if (!name.value.trim()) { err.textContent = '請輸入課程名稱。'; name.focus(); return; }
            const body = { name: name.value.trim(), ends_on: end.value || null };
            const result = course
                ? await call(`/api/courses/${course.id}`, 'PUT', body)
                : await call('/api/courses', 'POST', body);
            if (!result.ok) { err.textContent = result.data.error || '儲存失敗，請稍後再試'; return; }
            dlg.close(result.data);
        }
        const dlg = UI.dialog({
            title: course ? '編輯課程' : '新課程', body: box, cancelValue: null,
            actions: [
                { label: '取消', value: null },
                { label: course ? '儲存' : '建立課程', kind: 'primary', value: () => { save(); return undefined; } },
            ],
        });
        box.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
        return dlg.result;
    }

    function courseOf(node) {
        const s = node.closest('[data-course]');
        return {
            id: s.dataset.course, name: s.dataset.name, endsOn: s.dataset.endsOn || '',
            active: Number(s.dataset.active), sessions: Number(s.dataset.sessions), subs: Number(s.dataset.subs),
        };
    }

    async function courseAction(button) {
        const c = courseOf(button), kind = button.dataset.courseAction;
        if (kind === 'edit') {
            const saved = await courseDialog(c);
            if (saved) done(`已更新課程「${saved.name}」`);
            return;
        }
        if (kind === 'end') {
            // 「還在寫的會自動交卷」 is true because the take page polls /api/quiz/<code>/status every 20 s
            // (take_quiz.html pollSessionStatus), inside the 60 s hand-in grace.
            const ok = await UI.ask(
                (c.active ? `底下 ${c.active} 個進行中或還沒開始的課堂會一起結束。學生不能再作答，還在寫的會自動交卷。` : '底下的課堂都已經結束了。')
                + '成績都會留著，之後可以「重新開啟」。',
                { title: `結束課程「${c.name}」？`, okText: '結束課程', danger: true });
            if (!ok) return;
        }
        if (kind === 'delete') {
            const ok = await UI.ask(
                c.sessions ? `會永久刪除這個課程的 ${c.sessions} 個課堂和 ${c.subs} 份作答紀錄，學生的成績單連結也會打不開。這個動作無法復原。`
                           : '這個課程還沒有課堂。',
                { title: `刪除課程「${c.name}」？`, okText: '刪除課程', danger: true, matchText: c.subs ? c.name : undefined });
            if (!ok) return;
        }
        const result = kind === 'delete'
            ? await call(`/api/courses/${c.id}`, 'DELETE', { confirm: true })
            : await call(`/api/courses/${c.id}/${kind}`, 'POST', {});
        if (!result.ok) { UI.toast(result.data.error || '操作失敗，請稍後再試', 'error'); return; }
        done(result.data.message || '已更新課程');
    }

    document.addEventListener('click', async (event) => {
        if (event.target.closest('[data-course-new]')) {
            const saved = await courseDialog(null);
            if (saved) done(`已建立課程「${saved.name}」`);
            return;
        }
        const button = event.target.closest('[data-course-action]');
        if (button) courseAction(button);
    });

    window.CourseActions = { dialog: courseDialog };
})();
