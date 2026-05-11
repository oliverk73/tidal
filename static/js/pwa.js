/* PWA registration + Android install-prompt button.
 *
 * - Registers /sw.js with site-root scope.
 * - On Android/Chrome captures the beforeinstallprompt event and shows a
 *   small dismissible "Install" button bottom-right. iOS doesn't fire this
 *   event; install there happens via Safari's share menu.
 * - When the SW updates in the background, a small "Update available"
 *   bar offers a one-click reload.
 */

(function () {
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((reg) => {
        // Detect when a new SW takes over and offer reload.
        reg.addEventListener('updatefound', () => {
          const sw = reg.installing;
          if (!sw) return;
          sw.addEventListener('statechange', () => {
            if (sw.state === 'installed' && navigator.serviceWorker.controller) {
              showUpdateBar(reg);
            }
          });
        });
      })
      .catch((err) => console.warn('[PWA] SW registration failed:', err));
  });

  // ---------- Install prompt (Android / desktop Chrome) ----------

  let deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', (e) => {
    // Don't show the browser's mini-infobar; we render our own button.
    e.preventDefault();
    deferredPrompt = e;

    // Suppress if user already dismissed in the last 30 days.
    const dismissed = parseInt(localStorage.getItem('pwa-install-dismissed-at') || '0', 10);
    if (dismissed && (Date.now() - dismissed) < 30 * 24 * 3600 * 1000) return;

    showInstallButton();
  });

  function showInstallButton() {
    if (document.getElementById('pwa-install-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'pwa-install-btn';
    btn.type = 'button';
    btn.innerHTML = '&#x2B07; Install app';
    btn.title = 'Install this site as an app on your device';
    Object.assign(btn.style, {
      position: 'fixed',
      bottom: '64px',
      right: '14px',
      zIndex: '1000',
      background: '#169ca5',
      color: 'white',
      border: 'none',
      borderRadius: '24px',
      padding: '10px 18px',
      fontSize: '0.95em',
      fontWeight: '500',
      boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
      cursor: 'pointer',
    });

    const close = document.createElement('span');
    close.innerHTML = '&times;';
    Object.assign(close.style, {
      marginLeft: '10px', opacity: '0.75', fontSize: '1.2em',
    });
    close.addEventListener('click', (e) => {
      e.stopPropagation();
      localStorage.setItem('pwa-install-dismissed-at', String(Date.now()));
      btn.remove();
    });
    btn.appendChild(close);

    btn.addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      console.log('[PWA] install outcome:', outcome);
      deferredPrompt = null;
      btn.remove();
    });

    document.body.appendChild(btn);
  }

  window.addEventListener('appinstalled', () => {
    const btn = document.getElementById('pwa-install-btn');
    if (btn) btn.remove();
    console.log('[PWA] app installed');
  });

  // ---------- Update bar ----------

  function showUpdateBar(reg) {
    if (document.getElementById('pwa-update-bar')) return;
    const bar = document.createElement('div');
    bar.id = 'pwa-update-bar';
    bar.innerHTML = 'A newer version is available. <button id="pwa-update-btn" type="button">Reload</button>';
    Object.assign(bar.style, {
      position: 'fixed', top: '0', left: '0', right: '0',
      background: '#169ca5', color: 'white', padding: '10px 14px',
      fontSize: '0.95em', textAlign: 'center', zIndex: '2000',
      boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
    });
    document.body.appendChild(bar);
    document.getElementById('pwa-update-btn').addEventListener('click', () => {
      if (reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' });
      window.location.reload();
    });
  }

  // Listen for SKIP_WAITING handshake from SW (used if we later add that).
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (window.__pwaReloading) return;
    window.__pwaReloading = true;
  });
})();
