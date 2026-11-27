/* Markdown import preview table, shared by the create page and the manage page append tab.
 *
 * MdPreview.render(prefix, data, typeNames, offset) fills (offset = questions already in the Quiz Bank):
 *   #<prefix>-preview-body   the <tbody>; a question with a problem gets tr.is-error and its reasons
 *   #<prefix>-problems       the note under the table (hidden when there is no problem)
 *   #<prefix>-problem-list   the question numbers inside that note
 * It returns the number of questions with a problem.
 */
(function () {
    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }

    function row(item, typeNames, offset) {
        const errors = item.errors || [];
        const bad = errors.length > 0;
        const type = item.question_type
            ? `<span class="tb t-${esc(item.question_type)}">${esc(typeNames[item.question_type] || item.question_type)}</span>`
            : '<span class="muted">—</span>';
        const answer = bad
            ? `<span class="danger-text">${errors.map(esc).join('<br>')}</span>`
            : esc(item.answer);
        const state = bad
            ? '<i class="fas fa-exclamation-circle danger-text" aria-label="有問題"></i>'
            : '<i class="fas fa-check ok-text" aria-label="沒有問題"></i>';
        return `
            <tr class="${bad ? 'is-error' : ''}">
                <td class="num">${esc(offset + item.index)}</td>
                <td>${type}</td>
                <td class="t-title">${esc(item.title) || '<span class="muted">（沒有標題）</span>'}</td>
                <td>${item.category ? esc(item.category) : '<span class="muted">未分類</span>'}</td>
                <td class="num">${esc(item.points)}</td>
                <td>${answer}</td>
                <td>${state}</td>
            </tr>`;
    }

    function render(prefix, data, typeNames, offset) {
        const rows = data.questions || [];
        const start = offset || 0;
        document.getElementById(`${prefix}-preview-body`).innerHTML = rows.map(item => row(item, typeNames || {}, start)).join('');
        const badNumbers = rows.filter(item => (item.errors || []).length).map(item => start + item.index);
        const note = document.getElementById(`${prefix}-problems`);
        document.getElementById(`${prefix}-problem-list`).textContent = badNumbers.join('、');
        note.hidden = badNumbers.length === 0;
        return badNumbers.length;
    }

    window.MdPreview = { render };
})();
