(function () {
  'use strict';
  var data = null;
  var receivedAt = 0;
  var serverTime = 0;
  var failed = false;
  var pragueOffset = 0;
  var activeStage = '';
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
  function render() {
    var school = document.getElementById('homework'); school.textContent = '';
    var today = data.generated_at.slice(0, 10);
    data.homework.forEach(function (task) {
      school.appendChild(item(task.due === today ? 'Dnes' : 'Zítra', task.subject, task.title));
    });
    var events = document.getElementById('events'); events.textContent = '';
    data.events.forEach(function (event) { events.appendChild(item(event.time, event.title, '')); });
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
    document.getElementById('connection').className = stale ? 'connection error' : 'connection';
    text('connection', stale ? 'Spojení vypadlo · Časy teď nejsou ověřené' : '');
    if (stale) {
      text('minutes', '—'); text('departure', 'Čekáme na spojení');
      showStage('waiting', 'Čas ověří dospělý'); blocks(0, '', true);
      return;
    }
    var seconds = (Date.parse(data.transport.departures[0]) - now) / 1000;
    var stage = 'waiting';
    var until = now;
    for (var i = 0; i < data.routine.length; i += 1) {
      if (now < data.routine[i].until) { stage = data.routine[i].id; until = data.routine[i].until; break; }
    }
    text('minutes', Math.max(0, Math.ceil(seconds / 60)));
    text('departure', 'Odjezd ' + timeLabel(data.transport.departures[0]));
    var remaining = Math.max(0, Math.ceil((until - now) / 60000));
    var detail = stage === 'relax' ? 'Oblékání za ' + remaining + ' min' :
      stage === 'dress' ? 'Na oblečení ' + remaining + ' min' :
      stage === 'shoes' ? 'Na boty ' + remaining + ' min' :
      stage === 'go' ? 'S dospělým na zastávku' : 'Čekáme na další autobus';
    showStage(stage, detail); blocks(seconds, stage, false);
  }
  function refresh() {
    var request = new XMLHttpRequest();
    request.open('GET', '/api/dashboard', true); request.timeout = 8000;
    request.onload = function () {
      try {
        if (request.status !== 200) { throw new Error('Unavailable'); }
        var next = JSON.parse(request.responseText);
        if (next.source !== 'mock' || !next.transport.departures.length ||
            !next.routine || next.routine.length !== 4 || isNaN(Date.parse(next.generated_at))) {
          throw new Error('Invalid sample data');
        }
        data = next; receivedAt = elapsedTime(); serverTime = Date.parse(data.generated_at);
        var offset = data.generated_at.slice(-6);
        pragueOffset = (Number(offset.slice(1, 3)) * 60 + Number(offset.slice(4, 6))) * 60000 * (offset.charAt(0) === '-' ? -1 : 1);
        failed = false; render();
      } catch (error) { unavailable(); }
    };
    request.onerror = unavailable; request.ontimeout = unavailable;
    request.onloadend = function () { window.setTimeout(refresh, 15000); };
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
