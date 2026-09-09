(function () {
  'use strict';

  const PRODUCTION_HOST = 'preditor-fcu-v2.vercel.app';
  const ENDPOINT = 'https://preditor-fcu-master.vercel.app/api/collect';
  const VISITOR_KEY = 'preditor_visitor_id_v1';
  const SESSION_KEY = 'preditor_session_id_v1';
  const SESSION_SENT_KEY = 'preditor_session_started_v1';
  const OPTOUT_KEY = 'preditor_analytics_optout';
  if (window.location.hostname !== PRODUCTION_HOST) return;
  if (window.localStorage.getItem(OPTOUT_KEY) === '1') return;

  function identifier(prefix) {
    const value = window.crypto && typeof window.crypto.randomUUID === 'function'
      ? window.crypto.randomUUID().replaceAll('-', '')
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
    return `${prefix}_${value}`.slice(0, 80);
  }

  function storedId(storage, key, prefix) {
    let value = storage.getItem(key);
    if (!value || !/^[a-zA-Z0-9_-]{16,80}$/.test(value)) {
      value = identifier(prefix);
      storage.setItem(key, value);
    }
    return value;
  }

  const visitorId = storedId(window.localStorage, VISITOR_KEY, 'visitor');
  const sessionId = storedId(window.sessionStorage, SESSION_KEY, 'session');
  let lastActivity = Date.now();
  let lastHeartbeat = Date.now();
  let lastArea = '';
  let lastCell = '';

  function pageType() {
    const path = window.location.pathname.toLowerCase();
    if (path.includes('guia')) return 'guia';
    if (path.includes('3d')) return '3d';
    if (path.includes('privacidade')) return 'privacidade';
    return 'mapa';
  }

  function currentArea() {
    const params = new URLSearchParams(window.location.search);
    const queryArea = params.get('area');
    if (queryArea) return queryArea.slice(0, 160);
    try {
      if (window.App && window.App.currentPolo && window.App.currentPolo.area_col) {
        return String(window.App.currentPolo.area_col).slice(0, 160);
      }
    } catch (_) {}
    const heading = document.querySelector('#polo-title');
    const text = heading && heading.textContent ? heading.textContent.trim() : '';
    return /selecione|select/i.test(text) ? '' : text.slice(0, 160);
  }

  function currentCell() {
    const params = new URLSearchParams(window.location.search);
    return (params.get('cell') || params.get('cell_id') || '').slice(0, 160);
  }

  function payload(eventName, properties, activeSeconds) {
    return {
      event_id: identifier('event'),
      visitor_id: visitorId,
      session_id: sessionId,
      occurred_at: new Date().toISOString(),
      event_name: eventName,
      path: `${window.location.pathname}${window.location.search}`.slice(0, 500),
      page_type: pageType(),
      area_slug: currentArea(),
      cell_id: currentCell() || lastCell,
      language: String(navigator.language || '').slice(0, 40),
      timezone: String(Intl.DateTimeFormat().resolvedOptions().timeZone || '').slice(0, 80),
      screen_width: Number(window.screen && window.screen.width) || 0,
      screen_height: Number(window.screen && window.screen.height) || 0,
      active_seconds: Math.max(0, Math.min(60, Number(activeSeconds) || 0)),
      properties: properties || {}
    };
  }

  function send(eventName, properties, options) {
    if (window.localStorage.getItem(OPTOUT_KEY) === '1') return;
    const body = JSON.stringify(payload(eventName, properties, options && options.activeSeconds));
    if (options && options.beacon && navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
      return;
    }
    fetch(ENDPOINT, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      keepalive: true,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body
    }).catch(function () {});
  }

  function markActivity() { lastActivity = Date.now(); }
  ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(function (name) {
    window.addEventListener(name, markActivity, { passive: true });
  });

  function recordArea() {
    const area = currentArea();
    if (area && area !== lastArea) {
      lastArea = area;
      send('area_select', { area: area });
    }
  }

  function recordCellFromPanel() {
    const details = document.querySelector('#local-details');
    const text = details && details.textContent ? details.textContent : '';
    const match = text.match(/\b\d{3,4}ME[A-Z0-9_]{8,}\b/i);
    if (match && match[0] !== lastCell) {
      lastCell = match[0].slice(0, 160);
      send('cell_open', { source: 'panel' });
    }
  }

  document.addEventListener('click', function (event) {
    const target = event.target && event.target.closest ? event.target.closest('a,button,[role="button"]') : null;
    if (!target) return;
    const href = target.tagName === 'A' ? String(target.href || '') : '';
    const label = String(target.getAttribute('aria-label') || target.title || target.textContent || '').trim().slice(0, 100);

    if (target.matches('.legend-layer-toggle')) {
      send('layer_toggle', {
        layer: String(target.dataset.layer || label || 'camada').slice(0, 100),
        enabled: target.getAttribute('aria-checked') !== 'true'
      });
      return;
    }
    if (target.matches('.legend-toggle')) {
      send('legend_toggle', { control: label || 'legenda' });
      return;
    }
    if (target.closest('#nav-container')) window.setTimeout(recordArea, 80);
    if (href && /(^|\/)3d(?:\.html)?(?:[?#]|$)/i.test(href)) send('open_3d', { source: 'link' });
    else if (href && /guia(?:\.html)?/i.test(href)) send('open_guide', { source: 'link' });
    else if (href && /google\.|streetview|maps\./i.test(href)) send('external_map', { destination: 'mapa_externo' });
    else if (target.closest('#map, .leaflet-container, .maplibregl-map')) {
      send('map_click', { control: label || 'mapa' });
      window.setTimeout(recordCellFromPanel, 250);
    } else if (/minimapa|overview|visão geral/i.test(label)) send('minimap_toggle', { control: label });
    else if (/menu|sidebar|recolher|expandir/i.test(label) || target.id === 'desktop-sidebar-toggle' || target.id === 'hamburger-btn') {
      send('sidebar_toggle', { control: label || target.id });
    }
  }, true);

  document.addEventListener('change', function (event) {
    const input = event.target;
    if (!input || !/^(checkbox|radio)$/i.test(input.type || '')) return;
    const labelElement = input.closest('label') || (input.id && document.querySelector(`label[for="${CSS.escape(input.id)}"]`));
    const label = String(labelElement ? labelElement.textContent : input.name || input.id || 'camada').trim().slice(0, 100);
    send('layer_toggle', { layer: label, enabled: Boolean(input.checked) });
  }, true);

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter') return;
    const input = event.target;
    if (input && (input.type === 'search' || /search/i.test(input.id || ''))) {
      send('search_used', { field: String(input.id || input.name || 'busca').slice(0, 80) });
    }
  }, true);

  window.addEventListener('popstate', function () { window.setTimeout(recordArea, 50); });
  window.addEventListener('hashchange', function () { window.setTimeout(recordArea, 50); });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      lastActivity = Date.now();
      lastHeartbeat = Date.now();
    }
  });

  window.setInterval(function () {
    const now = Date.now();
    const active = document.visibilityState === 'visible' && now - lastActivity < 65_000;
    if (active) {
      const seconds = Math.max(1, Math.min(30, Math.round((now - lastHeartbeat) / 1000)));
      send('heartbeat', {}, { activeSeconds: seconds });
    }
    lastHeartbeat = now;
    recordArea();
  }, 30_000);

  window.addEventListener('pagehide', function () {
    const now = Date.now();
    if (document.visibilityState !== 'hidden' || now - lastActivity < 65_000) {
      const seconds = Math.max(0, Math.min(30, Math.round((now - lastHeartbeat) / 1000)));
      if (seconds > 0) send('heartbeat', {}, { activeSeconds: seconds, beacon: true });
    }
  });

  if (!window.sessionStorage.getItem(SESSION_SENT_KEY)) {
    window.sessionStorage.setItem(SESSION_SENT_KEY, '1');
    send('session_start', { entry: pageType() });
  }
  send('page_view', { title: String(document.title || '').slice(0, 140) });
  lastArea = currentArea();
  lastCell = currentCell();

  window.PreditorTelemetry = Object.freeze({ track: send });

  document.addEventListener('DOMContentLoaded', function () {
    const details = document.querySelector('#local-details');
    if (details && window.MutationObserver) {
      new MutationObserver(recordCellFromPanel).observe(details, { childList: true, subtree: true, characterData: true });
    }
    recordArea();
  });
})();
