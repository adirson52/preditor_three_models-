(function () {
  'use strict';

  const PRODUCTION_HOST = 'preditor-fcu-v2.vercel.app';
  const ENDPOINT = 'https://preditor-fcu-master.vercel.app/api/collect';
  const TELEMETRY_VERSION = '2026-09-10.5';
  const PREVIOUS_COMPATIBLE_VERSION = '2026-09-10.4';
  const VISITOR_KEY = 'preditor_visitor_id_v1';
  const SESSION_KEY = 'preditor_session_id_v1';
  const SESSION_SENT_KEY = 'preditor_session_started_v1';
  const SESSION_LAST_KEY = 'preditor_session_last_seen_v1';
  const SESSION_AREAS_KEY = 'preditor_selected_areas_v1';
  const SESSION_VERSION_KEY = 'preditor_session_collector_version_v1';
  const TEST_TOKEN_KEY = 'preditor_test_mode_token_v1';
  const OPTOUT_KEY = 'preditor_analytics_optout';
  const LOCATION_PREFERENCE_KEY = 'preditor_location_preference_v1';
  const LOCATION_ATTEMPT_KEY = 'preditor_location_attempt_v1';
  const LOCATION_SENT_KEY = 'preditor_location_sent_v1';
  const LOCATION_PROMPT_KEY = 'preditor_location_prompt_v1';
  const LOCATION_BANNER_ID = 'preditor-location-consent';
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

  function resolveStorage(name) {
    try { return window[name]; } catch (_) { return null; }
  }

  const localStore = resolveStorage('localStorage');
  const sessionStore = resolveStorage('sessionStorage');
  const runtimePreferences = Object.create(null);
  let runtimeOptOut = false;
  let locationAttemptedInMemory = false;
  let locationSentInMemory = false;
  let locationPromptedInMemory = false;

  function storageGet(storage, key) {
    try { return storage.getItem(key) || ''; } catch (_) { return ''; }
  }

  function storageSet(storage, key, value) {
    try { storage.setItem(key, value); } catch (_) {}
  }

  function storageRemove(storage, key) {
    try { storage.removeItem(key); } catch (_) {}
  }

  function cookieGet(key) {
    try {
      const prefix = encodeURIComponent(key) + '=';
      const item = String(document.cookie || '').split(';').map(value => value.trim())
        .find(value => value.startsWith(prefix));
      return item ? decodeURIComponent(item.slice(prefix.length)) : '';
    } catch (_) { return ''; }
  }

  function cookieSet(key, value) {
    try {
      document.cookie = encodeURIComponent(key) + '=' + encodeURIComponent(value)
        + '; Path=/; Max-Age=31536000; SameSite=Lax; Secure';
    } catch (_) {}
  }

  function cookieRemove(key) {
    try {
      document.cookie = encodeURIComponent(key) + '=; Path=/; Max-Age=0; SameSite=Lax; Secure';
    } catch (_) {}
  }

  function preferenceGet(key) {
    return storageGet(localStore, key) || cookieGet(key) || runtimePreferences[key] || '';
  }

  function preferenceSet(key, value) {
    runtimePreferences[key] = value;
    storageSet(localStore, key, value);
    cookieSet(key, value);
  }

  function preferenceRemove(key) {
    delete runtimePreferences[key];
    storageRemove(localStore, key);
    cookieRemove(key);
  }

  function resetSession() {
    storageRemove(sessionStore, SESSION_KEY);
    storageRemove(sessionStore, SESSION_SENT_KEY);
    storageRemove(sessionStore, SESSION_LAST_KEY);
    storageRemove(sessionStore, SESSION_AREAS_KEY);
    storageRemove(sessionStore, SESSION_VERSION_KEY);
    storageRemove(sessionStore, LOCATION_ATTEMPT_KEY);
    storageRemove(sessionStore, LOCATION_SENT_KEY);
    storageRemove(sessionStore, LOCATION_PROMPT_KEY);
    locationAttemptedInMemory = false;
    locationSentInMemory = false;
    locationPromptedInMemory = false;
  }

  function configureTestMode() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('telemetry_test')) return storageGet(localStore, TEST_TOKEN_KEY);
    const supplied = String(url.searchParams.get('telemetry_test') || '');
    const previous = storageGet(localStore, TEST_TOKEN_KEY);
    if (supplied === 'off') {
      storageRemove(localStore, TEST_TOKEN_KEY);
      if (previous) resetSession();
    } else if (/^[a-zA-Z0-9_.-]{40,1000}$/.test(supplied)) {
      storageSet(localStore, TEST_TOKEN_KEY, supplied);
      if (supplied !== previous) resetSession();
    }
    url.searchParams.delete('telemetry_test');
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    return storageGet(localStore, TEST_TOKEN_KEY);
  }

  let testToken = configureTestMode();

  const storedSessionId = storageGet(sessionStore, SESSION_KEY);
  const storedSessionVersion = storageGet(sessionStore, SESSION_VERSION_KEY);
  if (storedSessionId
      && storedSessionVersion !== TELEMETRY_VERSION
      && storedSessionVersion !== PREVIOUS_COMPATIBLE_VERSION) {
    resetSession();
  }

  const previousSessionValue = storageGet(sessionStore, SESSION_LAST_KEY);
  const previousSessionActivity = previousSessionValue ? Number(previousSessionValue) : Number.NaN;
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

  const visitorId = storedId(localStore, VISITOR_KEY, 'visitor');
  let sessionId = storedId(sessionStore, SESSION_KEY, 'session');
  storageSet(sessionStore, SESSION_VERSION_KEY, TELEMETRY_VERSION);
  let lastActivity = Date.now();
  let lastHeartbeat = Date.now();
  let lastSessionActivity = Date.now();
  let lastSessionWrite = 0;
  let lastArea = '';
  const selectedAreas = new Set((function () {
    try {
      const value = JSON.parse(storageGet(sessionStore, SESSION_AREAS_KEY) || '[]');
      return Array.isArray(value) ? value.filter(item => typeof item === 'string').slice(0, 100) : [];
    } catch (_) { return []; }
  })());
  let lastCell = new URLSearchParams(window.location.search).get('cell') || '';
  let lastCellEventAt = 0;
  let lastPanelCell = '';
  let pendingCellSource = '';

  function noteSessionActivity(force) {
    const now = Date.now();
    lastSessionActivity = now;
    if (force || now - lastSessionWrite > 10_000) {
      storageSet(sessionStore, SESSION_LAST_KEY, String(now));
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
    const active = document.querySelector('#nav-container .btn-nav.active[data-polo]');
    if (active) {
      const label = String(active.textContent || active.dataset.polo || '').trim();
      if (label && !/^preditor fcu/i.test(label)) return label.slice(0, 160);
    }
    const queryArea = areaFromQuery();
    if (queryArea) return queryArea;
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
      properties: Object.assign({}, properties || {}, { telemetry_version: TELEMETRY_VERSION }),
      test_token: testToken
    };
  }

  function handleCollectorResponse(response) {
    if (!testToken || !response || !response.ok) return;
    response.json().then(function (data) {
      if (data && data.traffic_kind === 'real') {
        storageRemove(localStore, TEST_TOKEN_KEY);
        testToken = '';
        const badge = document.getElementById('preditor-test-mode');
        if (badge) badge.remove();
      }
    }).catch(function () {});
  }

  function privacySignalEnabled() {
    return navigator.globalPrivacyControl === true
      || String(navigator.doNotTrack || window.doNotTrack || '') === '1';
  }

  function collectionDisabled() {
    return runtimeOptOut || preferenceGet(OPTOUT_KEY) === '1' || privacySignalEnabled();
  }

  function deliver(eventName, properties, settings) {
    if (collectionDisabled()) return false;
    const body = JSON.stringify(payload(eventName, properties, settings));
    if (settings.beacon && navigator.sendBeacon) {
      const queued = navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
      if (queued) return true;
    }
    fetch(ENDPOINT, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      keepalive: true,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: body
    }).then(handleCollectorResponse).catch(function () {});
    return true;
  }

  function locationState(storageKey) {
    const memoryState = storageKey === LOCATION_ATTEMPT_KEY ? locationAttemptedInMemory
      : storageKey === LOCATION_SENT_KEY ? locationSentInMemory
        : storageKey === LOCATION_PROMPT_KEY ? locationPromptedInMemory : false;
    return memoryState || storageGet(sessionStore, storageKey) === sessionId;
  }

  function markLocationState(storageKey) {
    if (storageKey === LOCATION_ATTEMPT_KEY) locationAttemptedInMemory = true;
    else if (storageKey === LOCATION_SENT_KEY) locationSentInMemory = true;
    else if (storageKey === LOCATION_PROMPT_KEY) locationPromptedInMemory = true;
    storageSet(sessionStore, storageKey, sessionId);
  }

  function removeLocationBanner() {
    const banner = document.getElementById(LOCATION_BANNER_ID);
    if (banner) banner.remove();
  }

  function locationText(portuguese, english) {
    return String(document.documentElement.lang || '').toLowerCase().startsWith('en') ? english : portuguese;
  }

  function notifyLocationStatus(status, detail) {
    window.dispatchEvent(new CustomEvent('preditor:location-status', {
      detail: Object.assign({ status: status }, detail || {})
    }));
  }

  function coarseCoordinate(value, minimum, maximum) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < minimum || numeric > maximum) return null;
    return Number(numeric.toFixed(3));
  }

  function coarseAccuracy(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 0) return 150;
    return Math.min(100000, Math.max(150, Math.ceil(numeric / 50) * 50));
  }

  function captureDeviceLocation(position, source) {
    if (preferenceGet(LOCATION_PREFERENCE_KEY) !== 'accepted' || collectionDisabled()) return false;
    if (locationState(LOCATION_SENT_KEY)) return true;
    const coords = position && position.coords;
    const latitude = coarseCoordinate(coords && coords.latitude, -90, 90);
    const longitude = coarseCoordinate(coords && coords.longitude, -180, 180);
    if (latitude === null || longitude === null) {
      notifyLocationStatus('unavailable');
      return false;
    }
    const queued = deliver('location_context', {
      location_source: 'device',
      location_status: 'granted',
      location_lat: latitude,
      location_lng: longitude,
      location_accuracy_m: coarseAccuracy(coords && coords.accuracy),
      coordinate_precision: '3_decimals',
      capture_source: String(source || 'permission').slice(0, 40)
    }, {});
    if (!queued) return false;
    markLocationState(LOCATION_SENT_KEY);
    removeLocationBanner();
    notifyLocationStatus('granted', {
      accuracy_m: coarseAccuracy(coords && coords.accuracy)
    });
    return true;
  }

  function requestDeviceLocation(source, explicitConsent) {
    if (collectionDisabled()) {
      notifyLocationStatus('measurement_disabled');
      return false;
    }
    if (explicitConsent) preferenceSet(LOCATION_PREFERENCE_KEY, 'accepted');
    if (preferenceGet(LOCATION_PREFERENCE_KEY) !== 'accepted') return false;
    if (!navigator.geolocation) {
      markLocationState(LOCATION_ATTEMPT_KEY);
      notifyLocationStatus('unavailable');
      return false;
    }
    if (locationState(LOCATION_SENT_KEY) || locationState(LOCATION_ATTEMPT_KEY)) return true;
    markLocationState(LOCATION_ATTEMPT_KEY);
    navigator.geolocation.getCurrentPosition(
      function (position) { captureDeviceLocation(position, source); },
      function (error) {
        if (error && error.code === error.PERMISSION_DENIED) {
          preferenceSet(LOCATION_PREFERENCE_KEY, 'declined');
          notifyLocationStatus('denied');
        } else {
          notifyLocationStatus('unavailable');
        }
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 }
    );
    return true;
  }

  function showLocationBanner() {
    if (pageType() === 'privacidade' || !document.body || document.getElementById(LOCATION_BANNER_ID)
        || collectionDisabled()
        || locationState(LOCATION_PROMPT_KEY)
        || preferenceGet(LOCATION_PREFERENCE_KEY) === 'declined') return;
    markLocationState(LOCATION_PROMPT_KEY);
    if (!document.getElementById('preditor-location-consent-style')) {
      const style = document.createElement('style');
      style.id = 'preditor-location-consent-style';
      style.textContent = '.preditor-location-consent{position:fixed;left:50%;bottom:max(16px,env(safe-area-inset-bottom));z-index:11500;display:flex;align-items:center;gap:14px;width:min(720px,calc(100vw - 28px));padding:14px 16px;border:1px solid #cfe0e7;border-radius:14px;background:rgba(255,255,255,.98);color:#17384b;box-shadow:0 14px 42px rgba(6,44,69,.22);font:13px/1.4 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;transform:translateX(-50%)}.preditor-location-copy{min-width:0;flex:1}.preditor-location-copy strong,.preditor-location-copy span{display:block}.preditor-location-copy strong{margin-bottom:2px;color:#07324d;font-size:14px}.preditor-location-copy span{color:#5f7581}.preditor-location-actions{display:flex;align-items:center;gap:8px;flex:none}.preditor-location-actions button{min-height:38px;padding:0 13px;border:1px solid #bfd4dc;border-radius:9px;background:#fff;color:#17465c;font:700 12px/1 Inter,system-ui,sans-serif;cursor:pointer}.preditor-location-actions .preditor-location-allow{border-color:#087d99;background:#087d99;color:#fff}.preditor-location-actions button:focus-visible{outline:3px solid rgba(8,125,153,.28);outline-offset:2px}@media(max-width:620px){.preditor-location-consent{align-items:stretch;flex-direction:column;gap:10px;padding:13px}.preditor-location-actions{justify-content:flex-end}.preditor-location-actions button{flex:1}}';
      document.head.append(style);
    }
    const banner = document.createElement('aside');
    banner.id = LOCATION_BANNER_ID;
    banner.className = 'preditor-location-consent';
    banner.setAttribute('aria-label', locationText('Localização do acesso', 'Access location'));
    const copy = document.createElement('div');
    copy.className = 'preditor-location-copy';
    const title = document.createElement('strong');
    title.textContent = locationText('Localização aproximada', 'Approximate location');
    const description = document.createElement('span');
    description.textContent = locationText(
      'Se você permitir, registramos uma posição aproximada do aparelho por sessão. Sem permissão, usamos apenas a origem aproximada da rede.',
      'If allowed, we record one approximate device position per session. Otherwise, only approximate network origin is used.'
    );
    copy.append(title, description);
    const actions = document.createElement('div');
    actions.className = 'preditor-location-actions';
    const decline = document.createElement('button');
    decline.type = 'button';
    decline.textContent = locationText('Agora não', 'Not now');
    decline.addEventListener('click', function () {
      preferenceSet(LOCATION_PREFERENCE_KEY, 'declined');
      removeLocationBanner();
      notifyLocationStatus('declined');
    });
    const allow = document.createElement('button');
    allow.type = 'button';
    allow.className = 'preditor-location-allow';
    allow.textContent = locationText('Permitir', 'Allow');
    allow.addEventListener('click', function () {
      allow.disabled = true;
      decline.disabled = true;
      requestDeviceLocation('consent_banner', true);
      removeLocationBanner();
    });
    actions.append(decline, allow);
    banner.append(copy, actions);
    document.body.append(banner);
  }

  function startLocationFlow() {
    if (collectionDisabled()
        || locationState(LOCATION_SENT_KEY) || locationState(LOCATION_ATTEMPT_KEY)) return;
    const preference = preferenceGet(LOCATION_PREFERENCE_KEY);
    if (preference === 'declined') return;
    if (!navigator.geolocation) {
      if (preference === 'accepted') notifyLocationStatus('unavailable');
      return;
    }
    if (!navigator.permissions || typeof navigator.permissions.query !== 'function') {
      if (preference === 'accepted') requestDeviceLocation('saved_consent', false);
      else showLocationBanner();
      return;
    }
    navigator.permissions.query({ name: 'geolocation' }).then(function (permission) {
      if (permission.state === 'denied') {
        notifyLocationStatus('denied');
        return;
      }
      if (preference === 'accepted' && permission.state === 'granted') {
        requestDeviceLocation('saved_consent', false);
        return;
      }
      showLocationBanner();
    }).catch(function () {
      if (preference === 'accepted') requestDeviceLocation('saved_consent', false);
      else showLocationBanner();
    });
  }

  function scheduleLocationFlow() {
    window.setTimeout(startLocationFlow, 250);
  }

  function rotateSession(reason) {
    resetSession();
    sessionId = storedId(sessionStore, SESSION_KEY, 'session');
    storageSet(sessionStore, SESSION_VERSION_KEY, TELEMETRY_VERSION);
    lastSessionWrite = 0;
    lastArea = '';
    selectedAreas.clear();
    lastCell = '';
    lastCellEventAt = 0;
    lastPanelCell = '';
    pendingCellSource = '';
    lastActivity = Date.now();
    lastHeartbeat = lastActivity;
    storageSet(sessionStore, SESSION_SENT_KEY, '1');
    noteSessionActivity(true);
    deliver('session_start', { entry: pageType(), reason: reason || 'nova sessão' }, {});
    scheduleLocationFlow();
  }

  function ensureFreshSession() {
    const stored = storageGet(sessionStore, SESSION_LAST_KEY);
    const previous = stored ? Number(stored) : lastSessionActivity;
    if (!Number.isFinite(previous) || Date.now() - previous > SESSION_TIMEOUT_MS) {
      rotateSession('retorno após inatividade');
    }
  }

  function send(eventName, properties, options) {
    if (collectionDisabled()) return false;
    ensureFreshSession();
    noteSessionActivity(false);
    return deliver(eventName, properties, options || {});
  }

  function markActivity() {
    if (collectionDisabled()) return;
    ensureFreshSession();
    lastActivity = Date.now();
    noteSessionActivity(false);
  }
  ['pointerdown', 'keydown', 'scroll', 'touchstart'].forEach(function (name) {
    window.addEventListener(name, markActivity, { passive: true, capture: true });
  });

  function syncAreaState(areaValue) {
    const area = String(areaValue || currentArea() || '').trim().slice(0, 160);
    if (!area || area === lastArea) return area;
    if (lastArea) {
      lastCell = '';
      lastCellEventAt = 0;
      lastPanelCell = '';
      pendingCellSource = '';
    }
    lastArea = area;
    return area;
  }

  function recordAreaChoice(areaValue) {
    const area = syncAreaState(areaValue);
    if (!area || selectedAreas.has(area)) return;
    selectedAreas.add(area);
    storageSet(sessionStore, SESSION_AREAS_KEY, JSON.stringify(Array.from(selectedAreas).slice(-100)));
    send('area_select', {
      area: area,
      source: 'menu de áreas',
      explicit: true
    }, { area: area });
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
      storageRemove(localStore, TEST_TOKEN_KEY);
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
    if (rawTarget && rawTarget.closest
        && rawTarget.closest('#optout,#location-on,#location-off,#preditor-location-consent')) return;
    const searchResult = rawTarget && rawTarget.closest
      ? rawTarget.closest('#map-search-results .map-search-result, #search-results .chip')
      : null;
    if (searchResult) {
      const cellId = cellFromText(searchResult.dataset.id || searchResult.textContent);
      pendingCellSource = cellId ? 'busca' : '';
      send('search_result_select', {
        result_type: cellId ? 'celula' : 'localizacao'
      }, { cellId: cellId });
      return;
    }
    const target = rawTarget && rawTarget.closest ? rawTarget.closest('a,button,[role="button"],img[data-zoom]') : null;
    if (!target) return;
    const href = target.tagName === 'A' ? String(target.getAttribute('href') || target.href || '') : '';
    const label = String(target.getAttribute('aria-label') || target.title || target.textContent || target.alt || '').trim().slice(0, 100);
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
    const areaButton = target.closest('#nav-container .btn-nav[data-polo]');
    if (areaButton) {
      if (event.isTrusted) {
        const area = String(areaButton.textContent || areaButton.dataset.polo || '').trim();
        recordAreaChoice(area);
      }
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
    } else if (event.isTrusted) {
      send('ui_click', {
        control: label || String(target.id || 'controle').slice(0, 100),
        element: String(target.tagName || '').toLowerCase().slice(0, 30)
      }, { cellId: currentCell() });
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
    window.setTimeout(syncAreaState, 50);
  });
  window.addEventListener('hashchange', function () {
    window.setTimeout(syncAreaState, 50);
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
      if (collectionDisabled()) return;
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
    syncAreaState();
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

  if (!storageGet(sessionStore, SESSION_SENT_KEY)) {
    storageSet(sessionStore, SESSION_SENT_KEY, '1');
    send('session_start', { entry: pageType() });
  }
  send('page_view', { title: String(document.title || '').slice(0, 140) }, { cellId: currentCell() });

  window.PreditorTelemetry = Object.freeze({
    track: send,
    isTest: function () { return Boolean(testToken); },
    measurementEnabled: function () { return !collectionDisabled(); },
    setMeasurementEnabled: function (enabled) {
      runtimeOptOut = !enabled;
      if (enabled) {
        preferenceRemove(OPTOUT_KEY);
      } else {
        preferenceSet(OPTOUT_KEY, '1');
        preferenceRemove(LOCATION_PREFERENCE_KEY);
        removeLocationBanner();
      }
      resetSession();
      notifyLocationStatus(enabled ? 'measurement_enabled' : 'measurement_disabled');
      return Boolean(enabled);
    },
    requestLocation: function () { return requestDeviceLocation('privacy_control', true); },
    captureLocation: function (position, source) {
      return captureDeviceLocation(position, source || 'map_control');
    },
    declineLocation: function () {
      preferenceSet(LOCATION_PREFERENCE_KEY, 'declined');
      removeLocationBanner();
      notifyLocationStatus('declined');
    },
    locationPreference: function () {
      return preferenceGet(LOCATION_PREFERENCE_KEY) || 'unset';
    }
  });

  scheduleLocationFlow();

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
      new MutationObserver(function () { window.setTimeout(syncAreaState, 30); })
        .observe(nav, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    }
    installTestBadge();
    syncAreaState();
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
