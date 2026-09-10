(function () {
  'use strict';

  const ENDPOINT = 'https://preditor-fcu-master.vercel.app/api/feedback';
  const VISITOR_KEY = 'preditor_visitor_id_v1';
  const SESSION_KEY = 'preditor_session_id_v1';
  const TRIGGER_SELECTOR = '[data-feedback-source]';
  const REQUEST_TIMEOUT_MS = 15000;
  const ID_PATTERN = /^[a-zA-Z0-9_-]{16,80}$/;

  const TEXT = {
    pt: {
      trigger: 'Enviar mensagem',
      title: 'Envie sua mensagem',
      description: 'Compartilhe uma dúvida, sugestão ou relato sobre o mapa.',
      privacyNote: 'Seu nome e e-mail serão usados para responder à sua mensagem.',
      close: 'Fechar',
      name: 'Nome',
      email: 'E-mail',
      message: 'Mensagem',
      namePlaceholder: 'Como podemos chamar você?',
      emailPlaceholder: 'voce@exemplo.com',
      messagePlaceholder: 'Escreva sua mensagem',
      send: 'Enviar',
      sending: 'Enviando…',
      error: 'Não foi possível enviar agora. Verifique sua conexão e tente novamente.',
      shortName: 'Escreva pelo menos 2 caracteres.',
      shortMessage: 'Escreva pelo menos 3 caracteres.',
      successTitle: 'Mensagem enviada',
      successMessage: 'Obrigado pela mensagem e por contribuir com o Preditor FCU.',
      successClose: 'Concluir'
    },
    en: {
      trigger: 'Send a message',
      title: 'Send us a message',
      description: 'Share a question, suggestion, or note about the map.',
      privacyNote: 'Your name and email will be used to reply to your message.',
      close: 'Close',
      name: 'Name',
      email: 'Email',
      message: 'Message',
      namePlaceholder: 'How should we address you?',
      emailPlaceholder: 'you@example.com',
      messagePlaceholder: 'Write your message',
      send: 'Send',
      sending: 'Sending…',
      error: 'We could not send your message. Check your connection and try again.',
      shortName: 'Please enter at least 2 characters.',
      shortMessage: 'Please enter at least 3 characters.',
      successTitle: 'Message sent',
      successMessage: 'Thank you for your message and for contributing to Preditor FCU.',
      successClose: 'Done'
    }
  };

  let root = null;
  let panel = null;
  let form = null;
  let successView = null;
  let errorBox = null;
  let submitLabel = null;
  let spinner = null;
  let lastFocused = null;
  let activeContext = null;
  let activeSubmissionId = '';
  let submitController = null;
  let requestSequence = 0;
  let sentSuccessfully = false;
  const boundTriggers = new WeakSet();

  function currentLanguage() {
    return window.CURR_LANG === 'en' || document.documentElement.lang === 'en' ? 'en' : 'pt';
  }

  function copy() {
    return TEXT[currentLanguage()] || TEXT.pt;
  }

  function cleanMetadata(value, maxLength) {
    return String(value == null ? '' : value)
      .replace(/[\u0000-\u001f\u007f]/g, ' ')
      .trim()
      .slice(0, maxLength);
  }

  function storageGet(storage, key) {
    try { return storage.getItem(key) || ''; } catch (_) { return ''; }
  }

  function storageSet(storage, key, value) {
    try { storage.setItem(key, value); } catch (_) {}
  }

  function randomToken(prefix) {
    const value = window.crypto && typeof window.crypto.randomUUID === 'function'
      ? window.crypto.randomUUID().replace(/-/g, '')
      : Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
    return (prefix + '_' + value).slice(0, 80);
  }

  function submissionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return randomToken('feedback');
  }

  function storedId(storage, key, prefix) {
    let value = storageGet(storage, key);
    if (!ID_PATTERN.test(value)) {
      value = randomToken(prefix);
      storageSet(storage, key, value);
    }
    return value;
  }

  function contextFromTrigger(trigger) {
    const app = window.__PREDITOR_APP__ || {};
    const selected = app.selectedSample || {};
    const currentPolo = app.currentPolo || {};
    const query = new URLSearchParams(window.location.search);
    const activeArea = document.querySelector('#nav-container .btn-nav.active[data-polo]');
    const source = trigger && trigger.dataset.feedbackSource === 'cell' ? 'cell' : 'sidebar';
    const areaSlug = (trigger && trigger.dataset.feedbackAreaSlug) ||
      selected.scope || selected.a || currentPolo.area_col || query.get('area') ||
      (activeArea && activeArea.dataset.polo) || app.currentPoloName || '';
    const cellId = (trigger && trigger.dataset.feedbackCellId) || selected.id || query.get('cell') || '';

    return {
      source: source,
      area_slug: cleanMetadata(areaSlug, 160),
      cell_id: cleanMetadata(cellId, 160),
      path: cleanMetadata(window.location.pathname || '/', 500)
    };
  }

  function modalMarkup() {
    return '<div class="feedback-modal-root" id="feedback-modal-root" hidden>' +
      '<div class="feedback-modal-backdrop" data-feedback-close></div>' +
      '<section class="feedback-modal" role="dialog" aria-modal="true" aria-labelledby="feedback-modal-title" aria-describedby="feedback-modal-description feedback-privacy-note" tabindex="-1">' +
        '<button class="feedback-modal-close" type="button" data-feedback-close aria-label="Fechar"><span aria-hidden="true">×</span></button>' +
        '<div class="feedback-form-view">' +
          '<header class="feedback-modal-header">' +
            '<h2 class="feedback-modal-title" id="feedback-modal-title" data-feedback-text="title">Envie sua mensagem</h2>' +
            '<p class="feedback-modal-description" id="feedback-modal-description" data-feedback-text="description">Compartilhe uma dúvida, sugestão ou relato sobre o mapa.</p>' +
            '<p class="feedback-privacy-note" id="feedback-privacy-note" data-feedback-text="privacyNote">Seu nome e e-mail serão usados para responder à sua mensagem.</p>' +
          '</header>' +
          '<form class="feedback-form">' +
            '<div class="feedback-field">' +
              '<label for="feedback-name" data-feedback-text="name">Nome</label>' +
              '<input id="feedback-name" name="name" type="text" minlength="2" maxlength="120" autocomplete="name" required>' +
            '</div>' +
            '<div class="feedback-field">' +
              '<label for="feedback-email" data-feedback-text="email">E-mail</label>' +
              '<input id="feedback-email" name="email" type="email" maxlength="254" autocomplete="email" inputmode="email" required>' +
            '</div>' +
            '<div class="feedback-field">' +
              '<label for="feedback-message" data-feedback-text="message">Mensagem</label>' +
              '<textarea id="feedback-message" name="message" minlength="3" maxlength="2000" required></textarea>' +
            '</div>' +
            '<p class="feedback-error" id="feedback-error" role="alert" hidden></p>' +
            '<button class="feedback-submit" type="submit">' +
              '<span class="feedback-submit-label" data-feedback-text="send">Enviar</span>' +
              '<span class="feedback-spinner" aria-hidden="true" hidden></span>' +
            '</button>' +
          '</form>' +
        '</div>' +
        '<div class="feedback-success" role="status" tabindex="-1" hidden>' +
          '<span class="feedback-success-check" aria-hidden="true">✓</span>' +
          '<h2 class="feedback-success-title" data-feedback-text="successTitle">Mensagem enviada</h2>' +
          '<p class="feedback-success-message" data-feedback-text="successMessage">Obrigado pela mensagem e por contribuir com o Preditor FCU.</p>' +
          '<button class="feedback-success-close" type="button" data-feedback-close data-feedback-text="successClose">Concluir</button>' +
        '</div>' +
      '</section>' +
    '</div>';
  }

  function applyLanguage() {
    if (!root) return;
    const strings = copy();
    root.querySelectorAll('[data-feedback-text]').forEach(function (element) {
      const key = element.dataset.feedbackText;
      if (strings[key]) element.textContent = strings[key];
    });
    const closeButton = root.querySelector('.feedback-modal-close');
    if (closeButton) closeButton.setAttribute('aria-label', strings.close);
    const name = root.querySelector('#feedback-name');
    const email = root.querySelector('#feedback-email');
    const message = root.querySelector('#feedback-message');
    if (name) name.placeholder = strings.namePlaceholder;
    if (email) email.placeholder = strings.emailPlaceholder;
    if (message) message.placeholder = strings.messagePlaceholder;
    refreshTriggerLabels();
  }

  function refreshTriggerLabels(scope) {
    const strings = copy();
    const searchRoot = scope && scope.querySelectorAll ? scope : document;
    searchRoot.querySelectorAll(TRIGGER_SELECTOR).forEach(function (trigger) {
      trigger.textContent = strings.trigger;
      const accessibleContext = trigger.dataset.feedbackSource === 'cell'
        ? (currentLanguage() === 'en' ? ' about this cell' : ' sobre esta célula')
        : '';
      trigger.setAttribute('aria-label', strings.trigger + accessibleContext);
      trigger.setAttribute('aria-haspopup', 'dialog');
      trigger.setAttribute('aria-controls', 'feedback-modal-root');
    });
  }

  function setError(message) {
    errorBox.textContent = message || '';
    errorBox.hidden = !message;
  }

  function setLoading(loading) {
    form.setAttribute('aria-busy', loading ? 'true' : 'false');
    Array.prototype.forEach.call(form.elements, function (control) {
      control.disabled = loading;
    });
    submitLabel.textContent = loading ? copy().sending : copy().send;
    spinner.hidden = !loading;
  }

  function showFormView(reset) {
    const formView = root.querySelector('.feedback-form-view');
    if (reset) form.reset();
    formView.hidden = false;
    successView.hidden = true;
    sentSuccessfully = false;
    setError('');
    setLoading(false);
    const name = root.querySelector('#feedback-name');
    const message = root.querySelector('#feedback-message');
    if (name) name.setCustomValidity('');
    if (message) message.setCustomValidity('');
  }

  function showSuccess() {
    sentSuccessfully = true;
    root.querySelector('.feedback-form-view').hidden = true;
    successView.hidden = false;
    successView.focus();
  }

  function open(trigger) {
    if (!root) createModal();
    applyLanguage();
    activeContext = contextFromTrigger(trigger);
    activeSubmissionId = submissionId();
    lastFocused = trigger || document.activeElement;
    showFormView(sentSuccessfully);
    root.hidden = false;
    document.body.classList.add('feedback-modal-open');
    window.setTimeout(function () {
      const name = root.querySelector('#feedback-name');
      (name || panel).focus();
    }, 0);
  }

  function close() {
    if (!root || root.hidden) return;
    requestSequence += 1;
    if (submitController) {
      submitController.abort();
      submitController = null;
    }
    root.hidden = true;
    document.body.classList.remove('feedback-modal-open');
    if (lastFocused && document.contains(lastFocused) && typeof lastFocused.focus === 'function') {
      lastFocused.focus();
    }
  }

  function focusableElements() {
    return Array.prototype.filter.call(
      panel.querySelectorAll('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'),
      function (element) { return !element.closest('[hidden]'); }
    );
  }

  function handleKeydown(event) {
    if (!root || root.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = focusableElements();
    if (!focusable.length) {
      event.preventDefault();
      panel.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitController) return;

    const strings = copy();
    const name = form.elements.name.value.trim();
    const email = form.elements.email.value.trim();
    const message = form.elements.message.value.trim();
    form.elements.name.setCustomValidity(name.length < 2 ? strings.shortName : '');
    form.elements.message.setCustomValidity(message.length < 3 ? strings.shortMessage : '');
    if (!form.reportValidity()) return;

    const requestId = ++requestSequence;
    const context = activeContext || contextFromTrigger(null);
    const payload = {
      submission_id: activeSubmissionId || submissionId(),
      name: name.slice(0, 120),
      email: email.slice(0, 254),
      message: message.slice(0, 2000),
      source: context.source,
      page_type: 'mapa',
      area_slug: context.area_slug,
      cell_id: context.cell_id,
      path: context.path,
      visitor_id: storedId(window.localStorage, VISITOR_KEY, 'visitor'),
      session_id: storedId(window.sessionStorage, SESSION_KEY, 'session')
    };

    setError('');
    setLoading(true);
    const controller = new AbortController();
    submitController = controller;
    let timedOut = false;
    const timeout = window.setTimeout(function () {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(ENDPOINT, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        credentials: 'omit',
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      if (!response.ok) throw new Error('feedback_http_' + response.status);
      if (requestId !== requestSequence || root.hidden) return;
      showSuccess();
    } catch (error) {
      if (requestId !== requestSequence || root.hidden) return;
      if (error && error.name === 'AbortError' && !timedOut) return;
      setError(strings.error);
    } finally {
      window.clearTimeout(timeout);
      if (requestId === requestSequence) {
        submitController = null;
        if (!root.hidden && !sentSuccessfully) setLoading(false);
      }
    }
  }

  function bindTrigger(trigger) {
    if (!trigger || boundTriggers.has(trigger)) return;
    boundTriggers.add(trigger);
    refreshTriggerLabels(trigger.parentElement || document);
  }

  function bindFrom(node) {
    if (!node || node.nodeType !== 1) return;
    if (node.matches && node.matches(TRIGGER_SELECTOR)) bindTrigger(node);
    if (node.querySelectorAll) node.querySelectorAll(TRIGGER_SELECTOR).forEach(bindTrigger);
  }

  function createModal() {
    if (root) return;
    const holder = document.createElement('div');
    holder.innerHTML = modalMarkup();
    root = holder.firstElementChild;
    document.body.appendChild(root);
    panel = root.querySelector('.feedback-modal');
    form = root.querySelector('.feedback-form');
    successView = root.querySelector('.feedback-success');
    errorBox = root.querySelector('#feedback-error');
    submitLabel = root.querySelector('.feedback-submit-label');
    spinner = root.querySelector('.feedback-spinner');

    root.addEventListener('click', function (event) {
      if (event.target.closest('[data-feedback-close]')) close();
    });
    form.addEventListener('submit', handleSubmit);
    const name = root.querySelector('#feedback-name');
    const message = root.querySelector('#feedback-message');
    name.addEventListener('input', function () { name.setCustomValidity(''); });
    message.addEventListener('input', function () { message.setCustomValidity(''); });
    document.addEventListener('keydown', handleKeydown);
    applyLanguage();
  }

  function init() {
    createModal();
    bindFrom(document.body);
    // Delegation keeps both triggers working even when the dashboard replaces
    // or recreates part of the sidebar/popup while changing area or language.
    document.addEventListener('click', function (event) {
      const trigger = event.target && event.target.closest
        ? event.target.closest(TRIGGER_SELECTOR)
        : null;
      if (!trigger) return;
      event.preventDefault();
      open(trigger);
    });
    const observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(bindFrom);
      });
    });
    observer.observe(document.body, {childList: true, subtree: true});
    document.querySelectorAll('#btn-pt, #btn-en').forEach(function (button) {
      button.addEventListener('click', function () {
        window.setTimeout(applyLanguage, 0);
      });
    });
  }

  window.PreditorFeedback = {open: open, close: close};
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
