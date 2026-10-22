(function () {
  'use strict';
  var data = null;
  var receivedAt = 0;
  var serverTime = 0;
  var failed = false;
  var pragueOffset = 0;
  var activeStage = '';
  var weatherKey = '';
  var agendaLimit = 4;
  var weekdays = ['Neděle', 'Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota'];
  var stages = {
    relax: { title: 'Máme čas', icon: 'sun' },
    dress: { title: 'Oblékat', icon: 'shirt' },
    shoes: { title: 'Obouvat', icon: 'shoes' },
    go: { title: 'Jdeme!', icon: 'bus' },
    waiting: { title: 'Chvilku počkáme', icon: 'wait' }
  };
  function text(id, value) { document.getElementById(id).textContent = value; }
  function pad(value) { return value < 10 ? '0' + value : String(value); }
  function timeLabel(iso) { return iso.slice(11, 16); }
  function departureLabel(iso) {
    var today = data.generated_at.slice(0, 10);
    return (iso.slice(0, 10) === today ? '' : iso.slice(8, 10) + '. ' + iso.slice(5, 7) + '. ') + timeLabel(iso);
  }
  function elapsedTime() {
    return window.performance && window.performance.now ? window.performance.now() : Date.now();
  }
  function item(label, title, detail) {
    var row = document.createElement('div'); row.className = 'item';
    var badge = document.createElement('span'); badge.className = 'label'; badge.textContent = label;
    var content = document.createElement('div');
    var heading = document.createElement('strong'); heading.textContent = title;
    var note = document.createElement('p'); note.textContent = detail;
    content.appendChild(heading); content.appendChild(note); row.appendChild(badge); row.appendChild(content);
    return row;
  }
  function showStage(id, detail) {
    if (activeStage !== id) {
      activeStage = id;
      document.getElementById('action').className = 'action ' + id;
      document.getElementById('action-icon').src = '/static/icons/' + stages[id].icon + '.svg';
      text('action-title', stages[id].title);
      ['relax', 'dress', 'shoes', 'go'].forEach(function (name) {
        var step = document.getElementById('step-' + name);
        step.className = name === id ? 'active' : '';
        if (name === id) { step.setAttribute('aria-current', 'step'); }
        else { step.removeAttribute('aria-current'); }
      });
    }
    if (document.getElementById('action-detail').textContent !== detail) { text('action-detail', detail); }
  }
  function blocks(remaining, stage, unknown) {
    var bar = document.getElementById('time-blocks');
    var total = data.dressing_minutes + data.shoes_minutes + data.walking_minutes;
    var count = 14;
    if (!bar.children.length) {
      for (var n = 0; n < count; n += 1) { bar.appendChild(document.createElement('i')); }
    }
    var filled = unknown ? 0 : Math.max(0, Math.min(count, Math.ceil(remaining / (total * 60) * count)));
    for (var i = 0; i < count; i += 1) { bar.children[i].className = i < filled ? 'full' : ''; }
    bar.className = 'time-blocks ' + (unknown ? 'unknown' : stage);
    bar.setAttribute('aria-label', unknown ? 'Čas není dostupný' : 'Do autobusu zbývá ' + Math.max(0, Math.ceil(remaining / 60)) + ' minut');
  }
  function sourceLabel(state) {
    var label = state.source === 'mock' ? 'Ukázka' : state.source === 'scheduled' ? 'Jízdní řád' : 'Připojeno';
    if (state.status === 'disabled') { return 'Vypnuto'; }
    if (state.status === 'unavailable') { return 'Nedostupné'; }
    if (state.status === 'stale') { label += ' · Starší data'; }
    if (state.last_success) { label += ' · ' + timeLabel(state.last_success); }
    return label;
  }
  function showWeather(now, disconnected) {
    var state = data.integrations.weather;
    var weather = data.weather;
    var ready = !disconnected && state && state.status === 'available' && weather && Date.parse(weather.valid_until) > now;
    var key = ready ? JSON.stringify(weather) : 'unavailable:' + (state && state.status);
    if (key === weatherKey) { return; }
    weatherKey = key;
    var clothes = document.getElementById('weather-clothes'); clothes.textContent = '';
    text('weather-temperature', ready ? Math.round(weather.temperature) + '°' : '—');
    if (!ready) {
      text('weather-note', state && state.status === 'stale' ? 'Starší počasí · ověří dospělý' : 'Počasí není dostupné');
      return;
    }
    text('weather-note', 'Pocitově ' + Math.round(weather.feels_like) + '° · ' + (weather.wet ? 'Hrozí srážky' : 'Příští 3 hodiny'));
    var labels = {'winter-coat': 'Teplá bunda', jacket: 'Bunda', hoodie: 'Mikina', tshirt: 'Tričko', hat: 'Čepice', raincoat: 'Pláštěnka'};
    weather.clothing.forEach(function (name) {
      if (!labels[name]) { return; }
      var figure = document.createElement('div');
      var icon = document.createElement('img'); icon.src = '/static/icons/' + name + '.svg'; icon.alt = labels[name];
      var label = document.createElement('span'); label.textContent = labels[name];
      figure.appendChild(icon); figure.appendChild(label); clothes.appendChild(figure);
    });
  }
  function render() {
    var school = document.getElementById('homework'); school.textContent = '';
    data.homework.slice(0, agendaLimit).forEach(function (task) {
      var dueLabel = task.urgency === 'overdue' ? 'Po termínu' : task.urgency === 'today' ? 'Dnes' : task.urgency === 'tomorrow' ? 'Zítra' : task.due.slice(8, 10) + '. ' + task.due.slice(5, 7) + '.';
      var homeworkRow = item(dueLabel, task.subject, task.title);
      if (task.urgency === 'today' || task.urgency === 'tomorrow' || task.urgency === 'overdue') { homeworkRow.className += ' due-' + task.urgency; }
      school.appendChild(homeworkRow);
    });
    if (data.homework.length > agendaLimit) {
      var more = document.createElement('div'); more.className = 'homework-more';
      more.textContent = '+ ' + (data.homework.length - agendaLimit) + ' dalších úkolů v Bakalářích'; school.appendChild(more);
    }
    var events = document.getElementById('events'); events.textContent = '';
    data.events.slice(0, agendaLimit).forEach(function (event) {
      var eventRow = item(event.time, event.calendar + ' · ' + event.title, '');
      if (event.upcoming) { eventRow.className += ' upcoming'; }
      events.appendChild(eventRow);
    });
    if (data.events.length > agendaLimit) {
      var moreEvents = document.createElement('div'); moreEvents.className = 'homework-more';
      moreEvents.textContent = '+ ' + (data.events.length - agendaLimit) + ' dalších událostí'; events.appendChild(moreEvents);
    }
    ['school', 'calendar'].forEach(function (name) {
      text(name + '-status', sourceLabel(data.integrations[name]));
    });
    if (!data.homework.length) { school.appendChild(item('', data.integrations.school.status === 'available' ? 'Žádné úkoly' : 'Úkoly nejsou dostupné', '')); }
    if (!data.events.length) { events.appendChild(item('', data.integrations.calendar.status === 'available' ? 'Dnes nic naplánováno' : 'Kalendář není dostupný', '')); }
    text('transport-source', data.integrations.transport.source === 'mock' ? 'UKÁZKA · Smyšlené odjezdy' : data.integrations.transport.source === 'scheduled' ? 'Jízdní řád · Bez živého zpoždění' : sourceLabel(data.integrations.transport));
    text('following', ''); text('bus-line', '');
    if (data.transport) {
      text('transport-route', data.transport.origin + ' → ' + data.transport.destination);
      var details = data.transport.departure_details || {};
      var first = details[data.transport.departures[0]];
      if (data.integrations.transport.source === 'live') {
        text('transport-source', first && first.delay_minutes !== null && first.delay_minutes !== undefined ? 'IDESKA · Odhad · ' + (first.delay_minutes > 0 ? '+' : '') + first.delay_minutes + ' min' : 'Jízdní řád · Bez živého zpoždění');
      }
      text('bus-line', first ? first.line : '');
      if (data.integrations.transport.status === 'available') {
        text('following', 'Další: ' + data.transport.departures.slice(1, 3).map(function (iso) {
          return (details[iso] ? details[iso].line + ' · ' : '') + departureLabel(iso);
        }).join(' / '));
      }
    }
    text('updated', 'Obnoveno ' + timeLabel(data.generated_at));
    tick();
  }
  function tick() {
    if (!data) { return; }
    var elapsed = elapsedTime() - receivedAt;
    var now = serverTime + elapsed;
    // Server offset avoids reliance on Intl timezone support in older TV browsers.
    var local = new Date(now + pragueOffset);
    var hours = local.getUTCHours();
    var minutes = local.getUTCMinutes();
    text('clock', pad(hours) + ':' + pad(minutes));
    text('date', weekdays[local.getUTCDay()] + ' ' + local.getUTCDate() + '. ' + (local.getUTCMonth() + 1) + '.');
    document.getElementById('hour-hand').setAttribute('transform', 'rotate(' + ((hours % 12) * 30 + minutes / 2) + ' 100 100)');
    document.getElementById('minute-hand').setAttribute('transform', 'rotate(' + minutes * 6 + ' 100 100)');
    var stale = failed || elapsed > 45000;
    showWeather(now, stale);
    var mapTransport = data.transport;
    var mapDeparture = mapTransport && mapTransport.departures[0];
    var mapDetail = mapDeparture && (mapTransport.departure_details || {})[mapDeparture];
    if (window.HomeboardMap) {
      window.HomeboardMap.update(mapDetail, now, !stale && data.integrations.transport.status === 'available', mapDeparture);
    }
    text('bus-progress', 'Poloha není dostupná');
    document.getElementById('connection').className = stale ? 'connection error' : 'connection';
    text('connection', stale ? 'Spojení vypadlo · Časy teď nejsou ověřené' : '');
    if (stale) {
      text('minutes', '—'); text('following', ''); text('departure', 'Čekáme na spojení');
      showStage('waiting', 'Čas ověří dospělý'); blocks(0, '', true);
      return;
    }
    var transportState = data.integrations.transport;
    if (transportState.status !== 'available' || !data.transport || !data.transport.departures.length || !data.routine.length) {
      text('minutes', '—');
      text('departure', transportState.status === 'available' ? 'Žádný další odjezd' : sourceLabel(transportState));
      showStage('waiting', 'Čas ověří dospělý'); blocks(0, '', true);
      return;
    }
    var seconds = (Date.parse(data.transport.departures[0]) - now) / 1000;
    var stage = 'waiting';
    var until = now;
    for (var i = 0; i < data.routine.length; i += 1) {
      if (now < data.routine[i].until) { stage = data.routine[i].id; until = data.routine[i].until; break; }
    }
    var longWait = seconds > 99 * 60;
    text('minutes', Math.max(0, Math.ceil(seconds / (longWait ? 3600 : 60))));
    text('countdown-unit', longWait ? 'h' : 'min');
    var detail = (data.transport.departure_details || {})[data.transport.departures[0]];
    var live = detail && detail.delay_minutes !== null && detail.delay_minutes !== undefined;
    text('departure', 'Plán ' + departureLabel(detail && detail.scheduled_at ? detail.scheduled_at : data.transport.departures[0]) + ' · Odhad ' + (live ? departureLabel(data.transport.departures[0]) : '—'));
    var progress = detail && detail.progress;
    var positionFresh = progress && now - Date.parse(progress.observed_at) >= 0 && now - Date.parse(progress.observed_at) <= 75000;
    if (positionFresh) {
      var progressLabels = {approaching: '🚌 Na cestě', town: '🏘 Už je v Plané', crossing: '🚦 U přejezdu', waiting_crossing: '🚦 Čeká u přejezdu', passed: '🚌 Za přejezdem!', strkovska: '🚌 Na Strkovské · za přejezdem'};
      text('bus-progress', progressLabels[progress.state]);
      if (progress.passed_crossing && stage === 'relax') { stage = 'dress'; }
    }
    var remaining = Math.max(0, Math.ceil((until - now) / 60000));
    var detail = stage === 'relax' ? 'Oblékání za ' + remaining + ' min' :
      stage === 'dress' ? 'Na oblečení ' + remaining + ' min' :
      stage === 'shoes' ? 'Na boty ' + remaining + ' min' :
      stage === 'go' ? 'S dospělým na zastávku' : 'Čekáme na další autobus';
    if (positionFresh && progress.passed_crossing && stage === 'dress') { detail = 'Autobus je za přejezdem'; }
    showStage(stage, detail); blocks(seconds, stage, false);
  }
  function refresh() {
    var request = new XMLHttpRequest();
    request.open('GET', '/api/dashboard', true); request.timeout = 30000;
    request.onload = function () {
      try {
        if (request.status !== 200) { throw new Error('Unavailable'); }
        var next = JSON.parse(request.responseText);
        if (!next.integrations || !next.integrations.transport || !next.integrations.school ||
            !next.integrations.calendar || !next.routine || isNaN(Date.parse(next.generated_at))) {
          throw new Error('Invalid sample data');
        }
        data = next; receivedAt = elapsedTime(); serverTime = Date.parse(data.generated_at);
        var offset = data.generated_at.slice(-6);
        pragueOffset = (Number(offset.slice(1, 3)) * 60 + Number(offset.slice(4, 6))) * 60000 * (offset.charAt(0) === '-' ? -1 : 1);
        failed = false; render();
      } catch (error) { unavailable(); }
    };
    request.onerror = unavailable; request.ontimeout = unavailable;
    request.onloadend = function () {
      var interval = !failed && data && data.refresh_seconds === 10 ? 10000 : 15000;
      window.setTimeout(refresh, interval);
    };
    request.send();
  }
  function unavailable() {
    failed = true;
    if (!data) {
      text('connection', 'Spojení se nepodařilo · Zkoušíme znovu');
      document.getElementById('connection').className = 'connection error';
      showStage('waiting', 'Čas ověří dospělý');
    } else { tick(); }
  }
  window.setInterval(tick, 1000);
  refresh();
}());
