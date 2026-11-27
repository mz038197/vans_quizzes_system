/*
 * Student side of a Class Session with several Quiz Banks (ticket 10, #12).
 *
 * Kept in this browser only, per Class Session code:
 *   hub_name_<code>  {name, email}   typed once, filled in on every start page of that code
 *   hub_done_<code>  {<bank id>: {pct, url}}   「✓ 已交卷」 marks with the score and the Result Link
 *
 * Pages:
 *   templates/class_session_hub.html — #class-session-hub[data-hub-code]
 *   templates/_quiz_entry.html       — #student-info-section[data-hub-code] (start page)
 *   templates/take_quiz.html         — calls StudentHub.markDone(...) after a Hand-in
 */
(function () {
    function read(key) {
        try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { return null; }
    }
    function write(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode: no marks */ }
    }

    const nameKey = (code) => 'hub_name_' + code;
    const doneKey = (code) => 'hub_done_' + code;

    function savedStudent(code) { return read(nameKey(code)) || {}; }
    function rememberStudent(code, name, email) {
        const old = savedStudent(code);
        write(nameKey(code), { name: name, email: email === undefined ? (old.email || '') : email });
    }
    function doneMarks(code) { return read(doneKey(code)) || {}; }
    function markDone(code, bankId, pct, url) {
        if (!code) return;
        const marks = doneMarks(code);
        marks[String(bankId)] = { pct: pct, url: url };
        write(doneKey(code), marks);
    }

    function setupHub(root) {
        const code = root.dataset.hubCode;
        const input = document.getElementById('hub-name');
        const saved = savedStudent(code);
        if (saved.name) input.value = saved.name;
        input.addEventListener('input', () => rememberStudent(code, input.value.trim()));

        const marks = doneMarks(code);
        root.querySelectorAll('.hub-item[data-bank]').forEach((item) => {
            const mark = marks[item.dataset.bank];
            if (!mark) return;
            item.classList.add('is-done');
            item.querySelector('.hub-ic i').className = 'fas fa-check';
            item.querySelector('.hub-go').hidden = true;
            const done = item.querySelector('.hub-done');
            done.hidden = false;
            if (mark.pct != null) done.querySelector('.hub-pct').textContent = Math.round(mark.pct) + '%';
            if (mark.url) {
                item.href = mark.url;
                done.insertAdjacentHTML('beforeend', '<span class="hub-link">看成績單 →</span>');
            }
        });

        root.addEventListener('click', (event) => {
            const item = event.target.closest('.hub-item');
            if (!item || item.classList.contains('is-done')) return;
            const name = input.value.trim();
            if (!name) {
                event.preventDefault();
                input.setAttribute('aria-invalid', 'true');
                UI.toast('請先輸入你的姓名', 'warn');
                input.focus();
                return;
            }
            rememberStudent(code, name);
        });
    }

    function setupStart(root) {
        const code = root.dataset.hubCode;
        const name = document.getElementById('student-name');
        const email = document.getElementById('student-email');
        const saved = savedStudent(code);
        if (name && !name.value && saved.name) name.value = saved.name;
        if (email && !email.value && saved.email) email.value = saved.email;
        const keep = () => rememberStudent(code, name ? name.value.trim() : '', email ? email.value.trim() : '');
        if (name) name.addEventListener('change', keep);
        if (email) email.addEventListener('change', keep);
    }

    document.addEventListener('DOMContentLoaded', () => {
        const hub = document.getElementById('class-session-hub');
        if (hub) setupHub(hub);
        const start = document.querySelector('#student-info-section[data-hub-code]');
        if (start) setupStart(start);
    });

    window.StudentHub = { markDone, rememberStudent, savedStudent, doneMarks };
})();
