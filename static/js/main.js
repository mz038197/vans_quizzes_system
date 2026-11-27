// Small shared helpers. Dialogs and toasts live in ui.js (window.UI), loaded before this file.

// JSON request helper.
async function makeRequest(url, method = 'GET', data = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (data) options.body = JSON.stringify(data);
    try {
        const response = await fetch(url, options);
        return { ok: response.ok, status: response.status, data: await response.json() };
    } catch (error) {
        return { ok: false, error: error.message };
    }
}

// Short message at the bottom of the page (kept for old callers; use UI.toast).
function showMessage(message, type = 'info', duration = 3000) {
    return window.UI.toast(message, type, { duration });
}

// Run callback after an in-page yes / no question (kept for old callers; use UI.ask).
async function confirmAction(message, callback, options) {
    if (await window.UI.ask(message, options)) callback();
}

function showFieldError(field, message) {
    field.classList.add('is-error');
    field.setAttribute('aria-invalid', 'true');
    const old = field.parentNode.querySelector('.err');
    if (old) old.remove();
    const errorEl = document.createElement('div');
    errorEl.className = 'err';
    errorEl.textContent = message;
    field.parentNode.appendChild(errorEl);
}

function clearFieldError(field) {
    field.classList.remove('is-error');
    field.removeAttribute('aria-invalid');
    const old = field.parentNode && field.parentNode.querySelector('.err');
    if (old) old.remove();
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Form check by rules: { name: { required, requiredMessage, minLength, email, validator } }.
function validateForm(formId, rules) {
    const form = document.getElementById(formId);
    if (!form) return false;
    let isValid = true;
    for (const fieldName in rules) {
        const field = form.querySelector(`[name="${fieldName}"]`);
        if (!field) continue;
        const rule = rules[fieldName];
        const value = field.value.trim();
        clearFieldError(field);
        let message = null;
        if (rule.required && !value) message = rule.requiredMessage || `${fieldName} 為必填欄位`;
        else if (rule.minLength && value.length < rule.minLength) message = rule.minLengthMessage || `${fieldName} 至少需要 ${rule.minLength} 個字`;
        else if (rule.email && value && !isValidEmail(value)) message = rule.emailMessage || '請輸入有效的電子郵件地址';
        else if (rule.validator && !rule.validator(value)) message = rule.validatorMessage || '輸入格式不正確';
        if (message) { showFieldError(field, message); isValid = false; }
    }
    return isValid;
}

// Show a spinner in a button while work runs.
function setButtonLoading(button, loading = true) {
    if (loading) {
        button.dataset.originalHtml = button.innerHTML;
        button.innerHTML = '<span class="spin" aria-hidden="true"></span> 處理中...';
        button.disabled = true;
    } else {
        if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
        button.disabled = false;
    }
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function throttle(func, limit) {
    let waiting = false;
    return function (...args) {
        if (waiting) return;
        func.apply(this, args);
        waiting = true;
        setTimeout(() => { waiting = false; }, limit);
    };
}

// Copy text. Returns true when it worked.
async function copyToClipboard(text) {
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            return true;
        }
    } catch (err) { /* fall through to the old way */ }
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.className = 'sr-only';
    document.body.appendChild(textArea);
    textArea.select();
    try {
        return document.execCommand('copy');
    } catch (err) {
        return false;
    } finally {
        textArea.remove();
    }
}

// Clear a field error when the field changes.
document.addEventListener('input', (event) => {
    if (event.target.matches && event.target.matches('.is-error')) clearFieldError(event.target);
});

window.QuizApp = {
    makeRequest,
    showMessage,
    validateForm,
    setButtonLoading,
    confirmAction,
    formatDate,
    debounce,
    throttle,
    copyToClipboard,
};
