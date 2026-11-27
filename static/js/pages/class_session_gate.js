/* 這堂課還沒開始: count down to the start, then reload; the server lets the student in from then on. */
(function () {
    const el = document.getElementById('gate-countdown');
    if (!el) return;
    // Seconds from the server, so a wrong computer clock does not matter.
    const target = Date.now() + (parseInt(el.dataset.startsIn, 10) || 0) * 1000;
    const pad = (n) => String(n).padStart(2, '0');

    function show(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h >= 24) {
            el.textContent = Math.floor(h / 24) + ' 天 ' + pad(h % 24) + ':' + pad(m) + ':' + pad(s);
        } else {
            el.textContent = (h ? pad(h) + ':' : '') + pad(m) + ':' + pad(s);
        }
    }

    function tick() {
        const left = Math.max(0, Math.ceil((target - Date.now()) / 1000));
        show(left);
        if (left <= 0) {
            clearInterval(timer);
            // A second of slack so the server clock has passed the start too.
            setTimeout(() => location.reload(), 1000);
        }
    }

    const timer = setInterval(tick, 1000);
    tick();
})();
