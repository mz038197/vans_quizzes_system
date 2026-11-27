/*
 * In-page dialogs and toasts (style A). Loaded by base.html and quiz_base.html before main.js.
 * The site never uses the browser's own alert / confirm / prompt boxes: use these instead.
 *
 *   UI.toast('已儲存', 'ok')                          short note at the bottom; types: info | ok | warn | error
 *   UI.toast('已移動', 'ok', { action: { label: '復原', onClick: undo }, duration: 6000 })
 *   await UI.tell('時間到，已自動繳交。')             message + one OK button; resolves when closed
 *   if (await UI.ask('確定要刪除嗎？', { danger: true, okText: '刪除' })) { ... }
 *   await UI.ask('刪除課堂', { matchText: '三年五班', ... })   OK stays disabled until the text is typed
 *   const name = await UI.askText('資料夾名稱', { value: '', placeholder: '...' })   null when cancelled
 *   const dlg = UI.dialog({ title, body: node|html, actions: [{ label, value, kind }] }); await dlg.result
 *   UI.flash('題庫已刪除', 'ok'); location.reload()    toast that shows after the next page load
 *   UI.setStudentName('王小明')                        fills the name in the student top bar
 *
 * Esc and the backdrop cancel a dialog (result false / null). Focus moves into the dialog,
 * stays in it while it is open, and goes back to the element that opened it.
 */
(function () {
    'use strict';

    const ICONS = { info: 'fa-info-circle', ok: 'fa-check-circle', warn: 'fa-exclamation-triangle', error: 'fa-times-circle' };
    const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        Object.entries(attrs || {}).forEach(([key, value]) => {
            if (value === undefined || value === null || value === false) return;
            if (key === 'text') node.textContent = value;
            else if (key === 'html') node.innerHTML = value;
            else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
            else node.setAttribute(key, value === true ? '' : value);
        });
        (children || []).forEach((child) => child && node.appendChild(child));
        return node;
    }

    /* ---------- toast ---------- */
    let toastRoot = null;
    function toastHost() {
        if (!toastRoot || !document.body.contains(toastRoot)) {
            toastRoot = el('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' });
            document.body.appendChild(toastRoot);
        }
        return toastRoot;
    }

    function toast(message, type, options) {
        type = ICONS[type] ? type : (type === 'success' ? 'ok' : type === 'warning' ? 'warn' : 'info');
        options = options || {};
        const duration = options.duration || (options.action ? 6000 : type === 'error' ? 5000 : 3000);
        const box = el('div', { class: 'toast toast-' + type });
        box.appendChild(el('i', { class: 'fas ' + ICONS[type], 'aria-hidden': 'true' }));
        box.appendChild(el('span', { text: String(message) }));
        let timer = null;
        const close = () => { clearTimeout(timer); box.remove(); };
        if (options.action) {
            box.appendChild(el('button', {
                type: 'button', class: 'toast-act', text: options.action.label,
                onclick: () => { close(); options.action.onClick && options.action.onClick(); },
            }));
        }
        box.appendChild(el('button', { type: 'button', class: 'toast-x', 'aria-label': '關閉', html: '<i class="fas fa-times" aria-hidden="true"></i>', onclick: close }));
        toastHost().appendChild(box);
        timer = setTimeout(close, duration);
        return { close };
    }

    /* ---------- dialog ---------- */
    let openCount = 0;

    function dialog(options) {
        options = options || {};
        const opener = document.activeElement;
        const titleId = 'dlg-t-' + Math.random().toString(36).slice(2);
        const box = el('div', {
            class: 'dlg' + (options.wide ? ' dlg-wide' : ''), role: options.role || 'dialog',
            'aria-modal': 'true', 'aria-labelledby': options.title ? titleId : null,
        });
        if (options.title) box.appendChild(el('h2', { id: titleId, text: options.title }));
        if (options.message) box.appendChild(el('p', { class: 'dlg-msg', text: options.message }));
        if (options.body) {
            if (typeof options.body === 'string') box.appendChild(el('div', { html: options.body }));
            else box.appendChild(options.body);
        }
        const actionsRow = el('div', { class: 'dlg-actions' });
        box.appendChild(actionsRow);
        const back = el('div', { class: 'dlg-back' }, [box]);

        let settle;
        const result = new Promise((resolve) => { settle = resolve; });
        let closed = false;
        function close(value) {
            if (closed) return;
            closed = true;
            document.removeEventListener('keydown', onKey, true);
            back.remove();
            openCount -= 1;
            if (openCount <= 0) { openCount = 0; document.body.classList.remove('has-dialog'); }
            if (opener && typeof opener.focus === 'function' && document.body.contains(opener)) opener.focus();
            settle(value);
        }
        const cancelValue = 'cancelValue' in options ? options.cancelValue : false;

        const buttons = (options.actions || [{ label: '確定', value: true, kind: 'primary' }]).map((action) => {
            const button = el('button', {
                type: 'button', class: 'btn' + (action.kind ? ' btn-' + action.kind : ''), text: action.label,
                onclick: () => {
                    const value = typeof action.value === 'function' ? action.value(box) : action.value;
                    if (value === undefined) return; // the action keeps the dialog open
                    close(value);
                },
            });
            if (action.disabled) button.disabled = true;
            actionsRow.appendChild(button);
            return button;
        });

        function onKey(event) {
            const backs = document.querySelectorAll('.dlg-back');
            if (backs[backs.length - 1] !== back) return; // only the top dialog takes keys
            if (event.key === 'Escape' && options.dismissible !== false) {
                event.preventDefault();
                close(cancelValue);
            } else if (event.key === 'Tab') {
                const items = Array.from(box.querySelectorAll(FOCUSABLE));
                if (!items.length) return;
                const first = items[0], last = items[items.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            }
        }
        back.addEventListener('mousedown', (event) => {
            if (event.target === back && options.dismissible !== false) close(cancelValue);
        });
        document.addEventListener('keydown', onKey, true);

        document.body.appendChild(back);
        openCount += 1;
        document.body.classList.add('has-dialog');
        const focusTarget = box.querySelector('[autofocus]') || box.querySelector('input, select, textarea')
            || buttons[typeof options.focusAction === 'number' ? options.focusAction : buttons.length - 1] || box;
        if (focusTarget === box) box.setAttribute('tabindex', '-1');
        focusTarget.focus();

        return { element: box, buttons, close, result };
    }

    /* Yes / no question. Resolves true (OK) or false (cancel, Esc, backdrop). */
    function ask(message, options) {
        options = options || {};
        let body = null;
        let input = null;
        if (options.matchText) {
            input = el('input', { class: 'inp', type: 'text', autocomplete: 'off', 'aria-label': '輸入名稱以確認' });
            body = el('div', { class: 'fld' }, [
                el('label', { html: '請輸入 <b></b> 以確認' }),
                input,
            ]);
            body.querySelector('b').textContent = options.matchText;
        }
        const d = dialog({
            title: options.title || (options.danger ? '請確認' : '確認'),
            message, body, role: 'alertdialog',
            focusAction: options.danger ? 0 : 1, // a dangerous action starts on 取消
            actions: [
                { label: options.cancelText || '取消', value: false },
                { label: options.okText || '確定', value: true, kind: options.danger ? 'danger' : 'primary', disabled: !!options.matchText },
            ],
        });
        if (input) {
            const ok = d.buttons[1];
            input.addEventListener('input', () => { ok.disabled = input.value.trim() !== options.matchText.trim(); });
            input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !ok.disabled) ok.click(); });
        }
        return d.result;
    }

    /* A message with one button. Resolves when it is closed. */
    function tell(message, options) {
        options = options || {};
        return dialog({
            title: options.title || '提示', message, role: 'alertdialog',
            actions: [{ label: options.okText || '知道了', value: true, kind: 'primary' }],
            cancelValue: true,
        }).result;
    }

    /* Ask for one line of text. Resolves the trimmed text, or null when cancelled. */
    function askText(title, options) {
        options = options || {};
        const input = el('input', { class: 'inp', type: 'text', value: options.value || '', placeholder: options.placeholder || '', autofocus: true });
        const field = el('div', { class: 'fld' }, [options.label ? el('label', { text: options.label }) : null, input]);
        const d = dialog({
            title, message: options.message, body: field, cancelValue: null,
            actions: [
                { label: options.cancelText || '取消', value: null },
                { label: options.okText || '確定', kind: 'primary', value: () => (input.value.trim() || (options.allowEmpty ? '' : undefined)) },
            ],
        });
        input.addEventListener('keydown', (event) => { if (event.key === 'Enter') d.buttons[1].click(); });
        return d.result;
    }

    function setStudentName(name) {
        document.querySelectorAll('[data-student-name]').forEach((node) => {
            node.textContent = name ? name : '';
        });
    }

    /* Toast shown on the next page load (for "save, then reload or go to another page"). */
    const FLASH_KEY = 'ui.flash';
    function flash(message, type) {
        try { sessionStorage.setItem(FLASH_KEY, JSON.stringify({ message, type })); } catch (err) { /* storage off */ }
    }
    function showFlash() {
        let item = null;
        try {
            item = JSON.parse(sessionStorage.getItem(FLASH_KEY) || 'null');
            sessionStorage.removeItem(FLASH_KEY);
        } catch (err) { item = null; }
        if (item && item.message) toast(item.message, item.type);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showFlash);
    else showFlash();

    /* Text → safe HTML text (for template strings that build innerHTML). The site's one escape helper. */
    function escape(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }

    window.UI = { toast, dialog, ask, tell, askText, flash, setStudentName, escape };
})();
