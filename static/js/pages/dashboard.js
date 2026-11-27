// 儀表板: 上課發題 panel (QR code, short link, copy, full-screen projector).
// The 「投影 QR」 buttons on the Class Session cards and the projector itself are in static/js/qr_stage.js.
(() => {
  const $ = (id) => document.getElementById(id);
  const select = $('qr-bank');
  const copyButton = $('qr-copy');
  let copyTimer = null;

  if (!select) return;
  const link = QrStage.link;

  function render() {
    $('qr-img').innerHTML = QrStage.svg(link(select.value));
    QrStage.shortLink($('qr-url'), select.value);
  }

  function resetCopy() {
    copyButton.classList.remove('is-ok');
    copyButton.querySelector('span').textContent = '複製連結';
  }

  copyButton.addEventListener('click', async () => {
    if (await copyToClipboard(link(select.value))) {
      copyButton.classList.add('is-ok');
      copyButton.querySelector('span').textContent = '已複製';
      clearTimeout(copyTimer);
      copyTimer = setTimeout(resetCopy, 1500);
    } else {
      UI.toast(`無法複製，請手動複製：${link(select.value)}`, 'error');
    }
  });

  select.addEventListener('change', () => { resetCopy(); render(); });
  $('qr-full').addEventListener('click', () => QrStage.open(select.value, select.selectedOptions[0].dataset.title));
  render();
})();
