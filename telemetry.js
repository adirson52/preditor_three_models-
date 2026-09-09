(function () {
  'use strict';

  const PRODUCTION_HOST = 'preditor-fcu-v2.vercel.app';
  const ENDPOINT = 'https://preditor-fcu-master.vercel.app/api/collect';
  const VISITOR_KEY = 'preditor_visitor_id_v1';
  const SESSION_KEY = 'preditor_session_id_v1';
  const SESSION_SENT_KEY = 'preditor_session_started_v1';
  const SESSION_LAST_KEY = 'preditor_session_last_seen_v1';
  const TEST_TOKEN_KEY = 'preditor_test_mode_token_v1';
  const OPTOUT_KEY = 'preditor_analytics_optout';
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
  const CELL_PATTERN = /\b\d{3,4}ME[A-Z0-9_]{8,}\b/i;
  const AREA_NAMES = {
    area_rgint_belem: 'Belém - RGInt',
    area_conc_urb_curitiba: 'Curitiba - Conc. Urbana',
    area_conc_urb_fortaleza: 'Fortaleza - Conc. Urbana',
    area_conc_urb_goiania: 'Goiânia - Conc. Urbana',
    area_rgint_macapa: 'Macapá - RGInt',
    area_rgint_redencao: 'Redenção - RGInt',
    area_arranjo_pop_rj: 'Rio de Janeiro - Arranjos Populacionais',
    area_conc_urb_rio_de_janeiro: 'Rio de Janeiro - Grande Conc. Urbana',
    area_medias_conc_urb_rj: 'Rio de Janeiro - Médias Conc. Urbanas',
    area_conc_urb_salvador: 'Salvador - Conc. Urbana',
    area_conc_urb_sao_paulo: 'São Paulo - Conc. Urbana'
  };

  if (window.location.hostname !== PRODUCTION_HOST) return;

  function storageGet(storage, key) {
    try { return storage.getItem(key) || ''; } catch (_) { return ''; }
  }

  function storageSet(storage, key, value) {
    try { storage.setItem(key, value); } catch (_) {}
  }

  function storageRemove(storage, key) {
    try { storage.removeItem(key); } catch (_) {}
  }

  function resetSession() {
    storageRemove(window.sessionStorage, SESSION_KEY);
    storageRemove(window.sessionStorage, SESSION_SENT_KEY);
    storageRemove(window.sessionStorage, SESSION_LAST_KEY);
  }

  function configureTestMode() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('telemetry_test')) return storageGet(window.localStorage, TEST_TOKEN_KEY);
    const supplied = String(url.searchParams.get('telemetry_test') || '');
    const previous = storageGet(window.localStorage, TEST_TOKEN_KEY);
    if (supplied === 'off') {
      storageRemove(window.localStorage, TEST_TOKEN_KEY);
      if (previous) resetSession();
    } else if (/^[a-zA-Z0-9_.-]{40,1000}$/.test(supplied)) {
      storageSet(window.localStorage, TEST_TOKEN_KEY, supplied);
      if (supplied !== previous) resetSession();
    }
    url.searchParams.delete('telemetry_test');
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    return storageGet(window.localStorage, TEST_TOKEN_KEY);
  }

  let testToken = configureTestMode();
  if (storageGet(window.localStorage, OPTOUT_KEY) === '1') return;

  const previousSessionActivity = Number(storageGet(window.sessionStorage, SESSION_LAST_KEY));
  if (!Number.isFinite(previousSessionActivity)
      || Date.now() - previousSessionActivity > SESSION_TIMEOUT_MS) {
    resetSession();
  }

  function identifier(prefix) {
    const value = window.crypto && typeof window.crypto.randomUUID === 'function'
      ? window.crypto.randomUUID().replaceAll('-', '')
      : Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
    return (prefix + '_' + value).slice(0, 80);
  }

  function storedId(storage, key, prefix) {
    let value = storageGet(storage, key);
    if (!value || !/^[a-zA-Z0-9_-]{16,80}$/.test(value)) {
      value = identifier(prefix);
      storageSet(storage, key, value);
    }
    return value;
  }

  const visitorId = storedId(window.localStorage, VISITOR_KEY, 'visitor');
  let sessionId = storedId(window.sessionStorage, SESSION_KEY, 'session');
  let lastActivity = Date.now();
  let lastHeartbeat = Date.now();
  let lastSessionWrite = 0;
  let lastArea = '';
  let lastCell = new URLSearchParams(window.location.search).get('cell') || '';
  let lastCellEventAt = 0;
  let lastPanelCell = '';
  let pendingCellSource = '';

  function noteSessionActivity(force) {
    const now = Date.now();
    if (force || now - lastSessionWrite > 10_000) {
      storageSet(window.sessionStorage, SESSION_LAST_KEY, String(now));
      lastSessionWrite = now;
    }
  }
  noteSessionActivity(true);

  function pageType() {
    const path = window.location.pathname.toLowerCase();
    if (path.includes('guia')) return 'guia';
    if (path.includes('3d')) return '3d';
    if (path.includes('privacidade')) return 'privacidade';
    return 'mapa';
  }

  function areaFromQuery() {
    const value = String(new URLSearchParams(window.location.search).get('area') || '').trim();
    if (!value) return '';
    if (AREA_NAMES[value]) return AREA_NAMES[value];
    if (/^area_[a-z0-9_]+$/i.test(value)) return value.slice(0, 160);
    if (!/^preditor fcu/i.test(value)) return value.slice(0, 160);
    return '';
  }

  function currentArea() {
    const queryArea = areaFromQuery();
    if (queryArea) return queryArea;
    const active = document.querySelector('#nav-container .btn-nav.active[data-polo]');
    if (active) {
      const label = String(active.textContent || active.dataset.polo || '').trim();
      if (label && !/^preditor fcu/i.test(label)) return label.slice(0, 160);
    }
    if (pageType() === '3d') return AREA_NAMES.area_conc_urb_salvador;
    return lastArea;
  }

  function currentCell() {
    return String(lastCell || '').slice(0, 160);
  }

  function cleanPath() {
    const url = new URL(window.location.href);
    url.searchParams.delete('telemetry_test');
    return (url.pathname + url.search).slice(0, 500);
  }

  function payload(eventName, properties, options) {
    const settings = options || {};
    return {
      event_id: identifier('event'),
      visitor_id: visitorId,
      session_id: sessionId,
      occurred_at: new Date().toISOString(),
      event_name: eventName,
      path: cleanPath(),
      page_type: pageType(),
      area_slug: String(settings.area || currentArea() || '').slice(0, 160),
      cell_id: String(settings.cellId || '').slice(0, 160),
      language: String(navigator.language || '').slice(0, 40),
      timezone: String(Intl.DateTimeFormat().resolvedOptions().timeZone || '').slice(0, 80),
      screen_width: Number(window.screen && window.screen.width) || 0,
      screen_height: Number(window.screen && window.screen.height) || 0,
      active_seconds: Math.max(0, Math.min(60, Number(settings.activeSeconds) || 0)),
      properties: properties || {},
      test_token: testToken
    };
  }

  function handleCollectorResponse(response) {
    if (!testToken || !response || !response.ok) return;
    response.json().then(function (data) {
      if (data && data.traffic_kind === 'real') {
        storageRemove(window.localStorage, TEST_TOKEN_KEY);
        testToken = '';
        const badge = document.getElementById('preditor-test-mode');
        if (badge) badge.remove();
      }
    }).catch(function () {});
  }

  function deliver(eventName, properties, settings) {
    const body = JSON.stringify(payload(eventName, properties, settings));
    if (settings.beacon && navigator.sendBeacon) {
      navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
      return;
    }
    fetch(ENDPOINT, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      keepalive: true,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: body
    }).then(handleCollectorResponse).catch(function () {});
  }

  function rotateSession(reason) {
    resetSession();
    sessionId = storedId(window.sessionStorage, SESSION_KEY, 'session');
    lastSessionWrite = 0;
    lastArea = '';
    lastCell = '';
    lastCellEventAt = 0;
    lastPanelCell = '';
    pendingCellSource = '';
    lastActivity = Date.now();
    lastHeartbeat = lastActivity;
    storageSet(window.sessionStorage, SESSION_SENT_KEY, '1');
    noteSessionActivity(true);
    deliver('session_start', { entry: pageType(), reason: reason || 'nova sessão' }, {});
  }

  function ensureFreshSession() {
    const previous = Number(storageGet(window.sessionStorage, SESSION_LAST_KEY));
    if (!Number.isFinite(previous) || Date.now() - previous > SESSION_TIMEOUT_MS) {
      rotateSession('retorno após inatividade');
    }
  }

  function send(eventName, properties, options) {
    if (storageGet(window.localStorage, OPTOUT_KEY) === '1') return;
    ensureFreshSession();
    noteSessionActivity(false);
    deliver(eventName, properties, options || {});
  }

  function markActivity() {
    ensureFreshSession();
    lastActivity = Date.now();
    noteSessionActivity(false);
  }
  ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(function (name) {
    window.addEventListener(name, markActivity, { passive: true, capture: true });
  });

  function recordArea(source) {
    const area = currentArea();
    if (area && area !== lastArea) {
      if (lastArea) {
        lastCell = '';
        lastCellEventAt = 0;
        lastPanelCell = '';
        pendingCellSource = '';
      }
      lastArea = area;
      send('area_select', { area: area, source: source || 'interface' }, { area: area });
    }
  }

  function cellFromText(value) {
    const match = String(value || '').match(CELL_PATTERN);
    return match ? match[0].slice(0, 160) : '';
  }

  function recordCell(cellId, source) {
    const cleanId = cellFromText(cellId);
    if (!cleanId) return;
    const now = Date.now();
    if (cleanId === lastCell && now - lastCellEventAt < 1500) return;
    lastCell = cleanId;
    lastCellEventAt = now;
    send('cell_open', { source: source || pendingCellSource || 'painel' }, { cellId: cleanId });
    pendingCellSource = '';
  }

  function recordCellFromPanel() {
    const details = document.querySelector('#local-details');
    const cellId = cellFromText(details && details.textContent);
    if (!cellId || cellId === lastPanelCell) return;
    lastPanelCell = cellId;
    recordCell(cellId, pendingCellSource || 'painel');
  }

  function rounded(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Number(numeric.toFixed(4)) : undefined;
  }

  function bindLeafletMap() {
    const app = window.__PREDITOR_APP__;
    if (!app || !app.map || app.map.__preditorTelemetryBound) return false;
    app.map.__preditorTelemetryBound = true;
    app.map.on('click', function (event) {
      pendingCellSource = 'mapa';
      const latlng = event && event.latlng;
      send('map_click', {
        lat: rounded(latlng && latlng.lat),
        lng: rounded(latlng && latlng.lng),
        zoom: Number(app.map.getZoom && app.map.getZoom()) || 0
      });
      window.setTimeout(recordCellFromPanel, 260);
    });
    return true;
  }

  function bindMapLibre3d() {
    const map = window.__RF_3D_MAP__;
    if (!map || map.__preditorTelemetryBound || typeof map.on !== 'function') return false;
    map.__preditorTelemetryBound = true;
    map.on('click', function (event) {
      let feature = null;
      try {
        feature = map.queryRenderedFeatures(event.point).find(function (item) {
          return item && item.properties && item.properties.cell_id;
        });
      } catch (_) {}
      const properties = feature && feature.properties ? feature.properties : {};
      const cellId = String(properties.cell_id || '');
      if (cellId) {
        lastCell = cellId.slice(0, 160);
        send('building_open_3d', {
          class: String(properties.class || '').slice(0, 60),
          zoom: Number(map.getZoom && map.getZoom()) || 0
        }, { cellId: lastCell });
      } else {
        const lngLat = event && event.lngLat;
        send('map_click', {
          lat: rounded(lngLat && lngLat.lat),
          lng: rounded(lngLat && lngLat.lng),
          zoom: Number(map.getZoom && map.getZoom()) || 0,
          view: '3d'
        });
      }
    });
    return true;
  }

  function chartLabel(plot) {
    const title = plot && plot.layout && plot.layout.title;
    const titleText = typeof title === 'string' ? title : title && title.text;
    return String(titleText || plot.id || 'grafico').replace(/<[^>]+>/g, '').slice(0, 100);
  }

  function bindPlots() {
    document.querySelectorAll('.js-plotly-plot').forEach(function (plot) {
      if (plot.dataset.telemetryBound === '1' || typeof plot.on !== 'function') return;
      plot.dataset.telemetryBound = '1';
      plot.on('plotly_click', function () {
        send('chart_interaction', { chart: chartLabel(plot) }, { cellId: currentCell() });
      });
    });
  }

  function installTestBadge() {
    if (!testToken || document.getElementById('preditor-test-mode')) return;
    const badge = document.createElement('div');
    badge.id = 'preditor-test-mode';
    badge.setAttribute('role', 'status');
    badge.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:99999;display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid rgba(120,73,7,.25);border-radius:10px;background:#fff2d8;color:#754408;box-shadow:0 8px 24px rgba(31,41,55,.18);font:800 11px/1.2 Inter,system-ui,sans-serif;letter-spacing:.03em;';
    const label = document.createElement('span');
    label.textContent = 'MODO TESTE';
    const exitButton = document.createElement('button');
    exitButton.type = 'button';
    exitButton.textContent = 'Encerrar';
    exitButton.style.cssText = 'border:0;border-radius:7px;padding:5px 7px;background:#754408;color:#fff;font:700 11px/1 Inter,system-ui,sans-serif;cursor:pointer;';
    exitButton.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      storageRemove(window.localStorage, TEST_TOKEN_KEY);
      resetSession();
      const url = new URL(window.location.href);
      url.searchParams.set('telemetry_test', 'off');
      window.location.replace(url.toString());
    });
    badge.append(label, exitButton);
    document.body.append(badge);
  }

  document.addEventListener('click', function (event) {
    const rawTarget = event.target;
    const target = rawTarget && rawTarget.closest ? rawTarget.closest('a,button,[role="button"],img[data-zoom]') : null;
    if (!target) return;
    const href = target.tagName === 'A' ? String(target.getAttribute('href') || target.href || '') : '';
    const label = String(target.getAttribute('aria-label') || target.title || target.textContent || target.alt || '').trim().slice(0, 100);

    const searchResult = target.closest('#map-search-results .map-search-result, #search-results .chip');
    if (searchResult) {
      const cellId = cellFromText(searchResult.dataset.id || searchResult.textContent);
      pendingCellSource = cellId ? 'busca' : '';
      send('search_result_select', {
        result_type: cellId ? 'celula' : 'localizacao'
      }, { cellId: cellId });
      return;
    }
    if (target.matches('.legend-layer-toggle')) {
      send('layer_toggle', {
        layer: String(target.dataset.layer || label || 'camada').slice(0, 100),
        enabled: target.getAttribute('aria-checked') !== 'true'
      });
      return;
    }
    if (target.matches('.legend-row')) {
      send('layer_toggle_3d', {
        layer: label || 'camada 3D',
        enabled: target.getAttribute('aria-pressed') !== 'true'
      });
      return;
    }
    if (target.matches('.legend-toggle, #legend-toggle')) {
      send('legend_toggle', { control: label || 'legenda' });
      return;
    }
    if (target.closest('#nav-container')) {
      window.setTimeout(function () { recordArea('menu de áreas'); }, 100);
      return;
    }
    if (target.matches('.map-size-button')) {
      send('map_expand', { control: label || 'mapa' });
      return;
    }
    if (target.matches('#map-search-toggle')) {
      send('search_toggle', { control: label || 'busca' });
      return;
    }
    if (target.matches('#back-to-2d')) {
      send('return_2d', { source: '3d' });
      return;
    }
    if (target.closest('.refresh-control')) {
      send('refresh_3d', { source: 'controle' });
      return;
    }
    if (target.matches('img[data-zoom]')) {
      send('guide_image_open', { image: label || 'imagem' });
      return;
    }
    if (target.closest('.section-nav') && href.startsWith('#')) {
      send('guide_section_open', { section: href.slice(1, 100) });
      return;
    }
    if (href && /(^|\/)3d(?:\.html)?(?:[?#]|$)/i.test(href)) {
      send('open_3d', { source: 'link' }, { cellId: currentCell() });
    } else if (href && /guia(?:\.html)?/i.test(href)) {
      send('open_guide', { source: 'link' });
    } else if (href && /google\.|streetview|maps\./i.test(href)) {
      const destination = /street/i.test(label + href) ? 'Street View' : 'Google Maps';
      send('external_map', { destination: destination }, { cellId: currentCell() });
    } else if (/minimapa|overview|visão geral/i.test(label)) {
      send('minimap_toggle', { control: label });
    } else if (/menu|sidebar|recolher|expandir/i.test(label)
      || target.id === 'desktop-sidebar-toggle' || target.id === 'hamburger-btn') {
      send('sidebar_toggle', { control: label || target.id });
    }
  }, true);

  document.addEventListener('change', function (event) {
    const input = event.target;
    if (!input) return;
    if (input.id === 'f-range') {
      send('stair_simulation', { f_percent: Math.max(0, Math.min(100, Number(input.value) || 0)) });
      return;
    }
    if (!/^(checkbox|radio)$/i.test(input.type || '')) return;
    const labelElement = input.closest('label')
      || (input.id && document.querySelector('label[for="' + CSS.escape(input.id) + '"]'));
    const label = String(labelElement ? labelElement.textContent : input.name || input.id || 'camada').trim().slice(0, 100);
    send('layer_toggle', { layer: label, enabled: Boolean(input.checked) });
  }, true);

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter') return;
    const input = event.target;
    if (!input || (input.type !== 'search' && !/search/i.test(input.id || ''))) return;
    const cellId = cellFromText(input.value);
    pendingCellSource = cellId ? 'busca' : '';
    send('search_used', {
      field: String(input.id || input.name || 'busca').slice(0, 80),
      recognized_cell: Boolean(cellId)
    }, { cellId: cellId });
  }, true);

  document.addEventListener('toggle', function (event) {
    const details = event.target;
    if (!details || details.tagName !== 'DETAILS' || !details.open) return;
    const summary = details.querySelector('summary');
    send('faq_open', { question: String(summary && summary.textContent || 'pergunta').trim().slice(0, 100) });
  }, true);

  window.addEventListener('popstate', function () {
    window.setTimeout(function () { recordArea('navegação'); }, 50);
  });
  window.addEventListener('hashchange', function () {
    window.setTimeout(function () { recordArea('navegação'); }, 50);
  });

  window.addEventListener('storage', function (event) {
    if ((event.key === TEST_TOKEN_KEY && String(event.newValue || '') !== testToken)
        || event.key === OPTOUT_KEY) {
      resetSession();
      window.location.reload();
    }
  });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      ensureFreshSession();
      lastActivity = Date.now();
      lastHeartbeat = Date.now();
      noteSessionActivity(true);
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
    recordArea('estado do mapa');
    bindLeafletMap();
    bindMapLibre3d();
    bindPlots();
  }, 30_000);

  window.addEventListener('pagehide', function () {
    const now = Date.now();
    noteSessionActivity(true);
    if (document.visibilityState !== 'hidden' || now - lastActivity < 65_000) {
      const seconds = Math.max(0, Math.min(30, Math.round((now - lastHeartbeat) / 1000)));
      if (seconds > 0) send('heartbeat', {}, { activeSeconds: seconds, beacon: true });
    }
  });

  if (!storageGet(window.sessionStorage, SESSION_SENT_KEY)) {
    storageSet(window.sessionStorage, SESSION_SENT_KEY, '1');
    send('session_start', { entry: pageType() });
  }
  send('page_view', { title: String(document.title || '').slice(0, 140) }, { cellId: currentCell() });

  window.PreditorTelemetry = Object.freeze({
    track: send,
    isTest: function () { return Boolean(testToken); }
  });

  document.addEventListener('DOMContentLoaded', function () {
    const details = document.querySelector('#local-details');
    if (details && window.MutationObserver) {
      new MutationObserver(recordCellFromPanel).observe(details, {
        childList: true,
        subtree: true,
        characterData: true
      });
    }
    const nav = document.querySelector('#nav-container');
    if (nav && window.MutationObserver) {
      new MutationObserver(function () { window.setTimeout(function () { recordArea('menu de áreas'); }, 30); })
        .observe(nav, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    }
    installTestBadge();
    recordArea('carregamento');
    let attempts = 0;
    const bindingTimer = window.setInterval(function () {
      attempts += 1;
      bindLeafletMap();
      bindMapLibre3d();
      bindPlots();
      if (attempts > 120) window.clearInterval(bindingTimer);
    }, 500);
  });
})();
