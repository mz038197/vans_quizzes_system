// Full-screen 投影 QR for a Class Session code (templates/_qr_stage.html).
// Any [data-qr="<code>"][data-title] button opens it. Links use the Class Session code.
(() => {
  const $ = (id) => document.getElementById(id);
  const stage = $('qr-stage');
  let opener = null;

  const link = (code) => `${location.origin}/quiz/${code}`;

  function svg(text) {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }

  function shortLink(target, code) {
    target.textContent = `${location.host}/quiz/`;
    const b = document.createElement('b');
    b.textContent = code;
    target.appendChild(b);
  }

  function open(code, title) {
    opener = document.activeElement;
    $('qr-stage-title').textContent = title;
    $('qr-stage-img').innerHTML = svg(link(code));
    shortLink($('qr-stage-url'), code);
    stage.hidden = false;
    document.body.classList.add('has-dialog');
    $('qr-close').focus();
    if (stage.requestFullscreen) stage.requestFullscreen().catch(() => {});
  }

  function close() {
    if (stage.hidden) return;
    stage.hidden = true;
    document.body.classList.remove('has-dialog');
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (opener) opener.focus();
  }

  document.addEventListener('click', (e) => {
    const button = e.target.closest('[data-qr]');
    if (button) open(button.dataset.qr, button.dataset.title);
  });
  $('qr-close').addEventListener('click', close);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) close(); });

  window.QrStage = { open, svg, link, shortLink };
})();
