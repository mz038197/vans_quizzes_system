/*
 * 課堂總表: select students and delete all their Submissions in this Class Session
 * (older Takes too). Markup: templates/grade_sheet.html; dialog and request: submission_delete.js.
 */
(function () {
    'use strict';

    const table = document.querySelector('table.sheet[data-class-session]');
    if (!table) return;
    const selectAll = table.querySelector('[data-select-all]');
    const boxes = [...table.querySelectorAll('[data-student]')];
    const UNIT = '位學生';

    function selectedStudents() {
        return boxes.filter(box => box.checked).map(box => box.dataset.student);
    }

    function refresh() {
        const count = selectedStudents().length;
        SubmissionDelete.syncSelectAll(selectAll, count, boxes.length);
        bar.show(count, UNIT);
    }

    async function deleteSelectedStudents() {
        const students = selectedStudents();
        const result = await SubmissionDelete.run(
            { class_session_id: Number(table.dataset.classSession), students },
            { count: students.length, names: students, unit: UNIT, scope: '在這堂課的所有作答（包括寫了好幾次的舊作答）' });
        if (!result) return;
        UI.flash(result.message, 'ok');
        location.reload();
    }

    function clearSelection() {
        boxes.forEach(box => { box.checked = false; });
        refresh();
    }

    const bar = SubmissionDelete.bar({ onDelete: deleteSelectedStudents, onClear: clearSelection });
    selectAll.addEventListener('change', () => {
        boxes.forEach(box => { box.checked = selectAll.checked; });
        refresh();
    });
    boxes.forEach(box => box.addEventListener('change', refresh));
})();
