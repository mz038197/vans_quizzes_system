/*
 * Shared 開課堂 dialog (ticket 09, #11). See templates/_class_session_dialog.html for how a page uses it.
 *
 * window.ClassSessionDialog.open({ bankIds, courseId }) → Promise<created Class Session | null>
 * window.ClassSessionDialog.open({ session }) → edit mode (#13); `session` is GET /api/class-sessions/<id>.
 *   Resolves to the saved Class Session or null. The Course cannot change; after the start, the start
 *   and the Time Limits of offered Quiz Banks are locked; removing a Quiz Bank with Submissions asks
 *   for its title to be typed and sends confirm: true.
 *
 * Parts that later tickets edit here (keep the names):
 *   renderPicker(state)  — how Quiz Banks are added. #11: a plain <select>. #12: searchable list grouped by Folder.
 *   renderChosen(state)  — the picked Quiz Banks with a Time Limit each.
 *   renderSummary(state) — the summary and the warnings under the times.
 *   PRESETS              — the quick time buttons.
 * Times in the inputs are UTC+8 wall clocks; the server reads a time without an offset as UTC+8.
 */
(function () {
    const MINUTE = 60e3;
    const UTC8 = 8 * 60 * MINUTE;

    function data() {
        const node = document.getElementById('cs-dialog-data');
        try { return JSON.parse(node ? node.textContent : '{}'); } catch (e) { return {}; }
    }

    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // ---- UTC+8 wall clock <-> epoch ms (independent of the computer's time zone) ----
    const toWall = (ms) => new Date(ms + UTC8).toISOString().slice(0, 16);
    const fromWall = (value) => {
        if (!value) return NaN;
        const ms = Date.parse(value + ':00Z');
        return Number.isNaN(ms) ? NaN : ms - UTC8;
    };
    /** epoch ms of hh:mm UTC+8 on the UTC+8 day `days` from today */
    function wallAt(days, hh, mm) {
        const today = new Date(Date.now() + UTC8);
        return Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + days, hh, mm) - UTC8;
    }
    function rangeText(a, b) {
        const da = new Date(a + UTC8), db = new Date(b + UTC8);
        const md = (d) => `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
        const hm = (d) => `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
        return md(da) === md(db) && Math.abs(b - a) < 86400e3
            ? `${md(da)} ${hm(da)}–${hm(db)}` : `${md(da)} ${hm(da)} – ${md(db)} ${hm(db)}`;
    }
    function lengthText(ms) {
        const m = Math.round(ms / MINUTE);
        if (m < 60) return `${m} 分鐘`;
        const h = Math.round(m / 6) / 10;
        if (h < 48) return `${h} 小時`;
        return `${Math.round(m / 1440)} 天`;
    }

    // ---- quick time buttons: [label, (state) => [start, end] or null when not available] ----
    const PRESETS = [
        ['now50', '現在開始・一節課 50 分鐘', () => [Date.now(), Date.now() + 50 * MINUTE]],
        ['today', '現在到今天 23:59', () => [Date.now(), wallAt(0, 23, 59)]],
        ['tomorrow', '明天 10:00–10:50', () => [wallAt(1, 10, 0), wallAt(1, 10, 50)]],
        ['term', '現在到學期末', (state) => {
            const course = state.course();
            return course && course.ends_at ? [Date.now(), fromWall(course.ends_at)] : null;
        }],
    ];

    function renderPicker(state) {
        const left = state.data.banks.filter((b) => !state.chosen.some((c) => c.id === b.id));
        state.$('pick').innerHTML = left.length
            ? '<option value="">＋ 加入題庫…</option>' + left.map((b) =>
                `<option value="${b.id}">${esc(b.title)}（${esc(b.mode)} · ${b.n_questions} 題）</option>`).join('')
            : '<option value="">所有題庫都已加入</option>';
        state.$('pick').disabled = !left.length;
    }

    function renderChosen(state) {
        const box = state.$('chosen');
        box.innerHTML = state.chosen.length ? state.chosen.map((c, i) => `
            <div class="csd-row">
                <span class="n num">${i + 1}</span>
                <div><b>${esc(c.title)}</b><span class="muted small">${c.n_subs ? `已有 ${c.n_subs} 份作答` : `${esc(c.mode)} · ${c.n_questions} 題`}</span></div>
                <label class="csd-lim">時限 <input class="inp" type="number" min="1" step="1" inputmode="numeric"
                    placeholder="不限" value="${c.limit == null ? '' : c.limit}" data-lim="${i}"${c.locked ? ' disabled title="課堂已開始，時限不能改"' : ''}
                    aria-label="「${esc(c.title)}」的時限（分鐘，空白是不限時）"> 分</label>
                <button type="button" class="btn btn-icon" data-unpick="${i}" aria-label="移除「${esc(c.title)}」"><i class="fas fa-times" aria-hidden="true"></i></button>
            </div>`).join('')
            : '<p class="muted small">還沒有選題庫。</p>';
        if (state.chosen.some((c) => c.locked)) {
            box.insertAdjacentHTML('beforeend', '<p class="muted small"><i class="fas fa-lock" aria-hidden="true"></i> 課堂已開始，開始時間和時限鎖住了。可以改名稱、結束時間，或加入、移除題庫。</p>');
        }
        renderPicker(state);
    }

    function renderSummary(state) {
        const a = fromWall(state.$('start').value), b = fromWall(state.$('end').value);
        const sum = state.$('sum');
        state.showError('');
        if (Number.isNaN(a) || Number.isNaN(b)) { sum.textContent = '選好開始和結束時間。'; return; }
        if (b <= a) { sum.textContent = ''; state.showError('結束時間要晚於開始時間。'); return; }
        if (b <= Date.now()) state.showError('結束時間已經過了，學生會打不開。');
        const limits = state.chosen.map((c) => c.limit).filter(Boolean);
        const longest = limits.length ? Math.max(...limits) : 0;
        sum.innerHTML = `學生在 <b>${rangeText(a, b)}</b> 之間可以作答（${lengthText(b - a)}），共 <b>${state.chosen.length} 份題庫</b>。`
            + (!state.editing && a <= Date.now() && b > Date.now() ? ' 建立後<b>馬上開始</b>。' : '')
            + (longest && longest * MINUTE > b - a
                ? `<br><span class="warn-text">注意：有題庫的時限 ${longest} 分鐘比開放時間長，課堂結束時就不能再交卷。</span>` : '');
    }

    function body(state) {
        const d = state.data;
        const courses = d.courses.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        const wrap = document.createElement('div');
        wrap.className = 'csd stack';
        wrap.innerHTML = `
            <div class="fld">
                <label for="csd-course">課程</label>
                <select class="inp" id="csd-course">${courses}<option value="new">＋ 新課程…</option></select>
                <input class="inp" id="csd-newcourse" placeholder="新課程名稱，例如：高一 3 班 · 115 上" hidden aria-label="新課程名稱">
            </div>
            <div class="fld">
                <label for="csd-name">課堂名稱</label>
                <input class="inp" id="csd-name" placeholder="例如：第 12 週 · 小考" autocomplete="off">
            </div>
            <div class="fld">
                <span class="csd-label">開放時間</span>
                <div class="csd-presets">${PRESETS.map(([k, label]) => `<button type="button" class="btn" data-preset="${k}">${label}</button>`).join('')}</div>
                <div class="grid-2">
                    <div class="fld"><label for="csd-start" class="small muted">開始</label><input class="inp" id="csd-start" type="datetime-local"></div>
                    <div class="fld"><label for="csd-end" class="small muted">結束</label><input class="inp" id="csd-end" type="datetime-local"></div>
                </div>
            </div>
            <div class="fld">
                <span class="csd-label">題庫 <span class="muted small">· 每份可以設自己的時限，空白是不限時</span></span>
                <div id="csd-chosen"></div>
                <select class="inp" id="csd-pick" aria-label="加入題庫"></select>
            </div>
            <div class="csd-sum" id="csd-sum" aria-live="polite"></div>
            <p class="err danger-text small" id="csd-err" role="alert"></p>`;
        return wrap;
    }

    async function submit(state, dlg) {
        const $ = state.$;
        const isNew = $('course').value === 'new';
        const name = $('name').value.trim();
        if (isNew && !$('newcourse').value.trim()) { state.showError('請輸入新課程的名稱。'); $('newcourse').focus(); return; }
        if (!name) { state.showError('請輸入課堂名稱。'); $('name').focus(); return; }
        if (!state.chosen.length) { state.showError('至少要選一份題庫。'); $('pick').focus(); return; }
        const okButton = dlg.buttons[dlg.buttons.length - 1];
        okButton.disabled = true;
        const editing = state.editing;
        try {
            const response = editing ? await fetch(`/api/class-sessions/${editing.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    starts_at: editing.started ? null : $('start').value,
                    ends_at: $('end').value,
                    banks: state.chosen.map((c) => ({ quiz_bank_id: c.id, time_limit_minutes: c.limit })),
                    confirm: state.confirmed,
                }),
            }) : await fetch('/api/class-sessions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    course_id: isNew ? null : Number($('course').value),
                    new_course_name: isNew ? $('newcourse').value.trim() : null,
                    name,
                    starts_at: $('start').value,
                    ends_at: $('end').value,
                    banks: state.chosen.map((c) => ({ quiz_bank_id: c.id, time_limit_minutes: c.limit })),
                }),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) { state.showError(result.error || '開課堂失敗，請稍後再試'); return; }
            dlg.close(result);
        } catch (e) {
            state.showError('網路錯誤，請稍後再試');
        } finally {
            okButton.disabled = false;
        }
    }

    function open(options) {
        options = options || {};
        const d = data();
        d.courses = d.courses || [];
        d.banks = d.banks || [];
        const byId = (id) => d.banks.find((b) => b.id === Number(id));
        const pick = (bank) => ({ ...bank, limit: bank.last_time_limit == null ? null : bank.last_time_limit });
        const editing = options.session || null;
        const offered = (o) => ({
            mode: '', n_questions: 0, ...(byId(o.quiz_bank_id) || {}), id: o.quiz_bank_id, title: o.title,
            limit: o.time_limit_minutes, n_subs: o.n_subs, locked: !!editing.started,
        });

        const state = {
            data: d,
            chosen: editing ? editing.banks.map(offered) : (options.bankIds || []).map(byId).filter(Boolean).map(pick),
            editing,
            confirmed: false,
            root: null,
            $: (id) => state.root.querySelector('#csd-' + id),
            course: () => d.courses.find((c) => String(c.id) === state.$('course').value) || null,
            showError: (text) => { state.$('err').textContent = text; },
        };

        const root = body(state);
        state.root = root;
        const startCourse = d.courses.some((c) => c.id === Number(options.courseId)) ? options.courseId : d.default_course_id;
        state.$('course').value = startCourse ? String(startCourse) : 'new';
        state.$('start').value = toWall(Date.now());
        state.$('end').value = toWall(Date.now() + 50 * MINUTE);
        if (editing) {
            // The Course is fixed after creation; show only that one.
            state.$('course').innerHTML = `<option value="${editing.course_id}">${esc(editing.course_name)}${editing.course_open ? '' : '（已結束）'}</option>`;
            state.$('course').disabled = true;
            state.$('course').insertAdjacentHTML('afterend', '<span class="help muted small">課堂建立後不能換課程。</span>');
            state.$('name').value = editing.name;
            state.$('start').value = editing.starts_at;
            state.$('end').value = editing.ends_at;
            state.$('start').disabled = !!editing.started;
            root.querySelector('.csd-presets').hidden = true;
        }

        function courseChanged() {
            const isNew = state.$('course').value === 'new';
            state.$('newcourse').hidden = !isNew;
            const term = root.querySelector('[data-preset="term"]');
            const course = state.course();
            term.disabled = !(course && course.ends_at);
            term.title = term.disabled ? '這個課程沒有結束日期' : '';
            renderSummary(state);
        }
        state.$('course').addEventListener('change', () => { courseChanged(); if (state.$('course').value === 'new') state.$('newcourse').focus(); });
        ['start', 'end'].forEach((k) => state.$(k).addEventListener('input', () => renderSummary(state)));
        state.$('pick').addEventListener('change', (e) => {
            const bank = byId(e.target.value);
            if (bank) { state.chosen.push(pick(bank)); renderChosen(state); renderSummary(state); }
        });
        root.addEventListener('input', (e) => {
            const i = e.target.dataset.lim;
            if (i === undefined) return;
            const v = parseInt(e.target.value, 10);
            state.chosen[Number(i)].limit = v > 0 ? v : null;
            renderSummary(state);
        });
        root.addEventListener('click', (e) => {
            const un = e.target.closest('[data-unpick]');
            if (un) {
                const index = Number(un.dataset.unpick), c = state.chosen[index];
                if (!c.n_subs) { state.chosen.splice(index, 1); renderChosen(state); renderSummary(state); return; }
                UI.ask(`這份題庫在這堂課已經有 ${c.n_subs} 份作答。儲存後，這些作答會永久刪除，學生的成績單連結也會打不開。`,
                    { title: `從課堂移除「${c.title}」？`, danger: true, okText: '移除並刪除作答', matchText: c.title })
                    .then((ok) => {
                        if (!ok) return;
                        state.confirmed = true;
                        state.chosen.splice(state.chosen.indexOf(c), 1);
                        renderChosen(state); renderSummary(state);
                    });
                return;
            }
            const p = e.target.closest('[data-preset]');
            if (p) {
                const preset = PRESETS.find(([k]) => k === p.dataset.preset);
                const range = preset && preset[2](state);
                if (!range) return;
                state.$('start').value = toWall(range[0]);
                state.$('end').value = toWall(range[1]);
                renderSummary(state);
            }
        });

        renderChosen(state);
        courseChanged();

        let dlg;
        dlg = UI.dialog({
            title: editing ? `編輯課堂「${editing.name}」` : '開課堂',
            body: root,
            wide: true,
            cancelValue: null,
            actions: [
                { label: '取消', value: null },
                { label: editing ? '儲存' : '開課堂', kind: 'primary', value: () => { submit(state, dlg); return undefined; } },
            ],
        });
        root.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.target.tagName === 'INPUT') { e.preventDefault(); submit(state, dlg); }
        });
        state.$('name').focus();
        return dlg.result;
    }

    // Any [data-open-session] button opens the dialog.
    document.addEventListener('click', async (event) => {
        const button = event.target.closest('[data-open-session]');
        if (!button) return;
        event.preventDefault();
        const bankIds = (button.dataset.openSession || '').split(',').map(Number).filter(Boolean);
        const created = await open({ bankIds, courseId: button.dataset.course });
        if (!created) return;
        UI.flash(`已在「${created.course_name}」開課堂「${created.name}」，代碼 ${created.code}`, 'ok');
        if (button.dataset.sessionReturn) location.href = button.dataset.sessionReturn;
        else location.reload();
    });

    window.ClassSessionDialog = { open, PRESETS, renderPicker, renderChosen, renderSummary, toWall, fromWall };
})();
