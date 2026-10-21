/* Fixed local SVG map. Coordinates share the source extract's linear projection. */
(function () {
  'use strict';
  var last = null;
  var selected = null;
  window.HomeboardMap = {
    update: function (detail, now, available, departure) {
      var map = document.getElementById('minimap');
      var marker = document.getElementById('map-bus');
      var label = document.getElementById('map-status');
      var key = detail && departure ? detail.line + ':' + detail.trip + ':' + (detail.scheduled_at || departure) : null;
      if (key !== selected) { last = null; selected = key; }
      var fix = detail && detail.progress;
      if (available && fix && typeof fix.latitude === 'number' && typeof fix.longitude === 'number' &&
          isFinite(fix.latitude) && isFinite(fix.longitude) && Date.parse(fix.observed_at) <= now) {
        last = {latitude: fix.latitude, longitude: fix.longitude, observedAt: Date.parse(fix.observed_at)};
      }
      marker.setAttribute('visibility', 'hidden');
      if (!last || !isFinite(last.observedAt) || now - last.observedAt > 300000 || now - last.observedAt < 0) {
        label.textContent = 'Poloha není dostupná';
        return;
      }
      var age = Math.floor((now - last.observedAt) / 1000);
      var stale = !available || !fix || typeof fix.latitude !== 'number' || typeof fix.longitude !== 'number' || age > 75;
      var west = Number(map.getAttribute('data-west'));
      var east = Number(map.getAttribute('data-east'));
      var north = Number(map.getAttribute('data-north'));
      var south = Number(map.getAttribute('data-south'));
      var x = (last.longitude - west) / (east - west) * 400;
      var y = (north - last.latitude) / (north - south) * 600;
      if (x < 0 || x > 400 || y < 0 || y > 600) {
        label.textContent = stale ? 'Poslední poloha mimo mapu · ' + age + ' s' : 'Autobus ještě mimo mapu';
        return;
      }
      marker.setAttribute('transform', 'translate(' + x + ' ' + y + ')');
      marker.setAttribute('visibility', 'visible');
      marker.setAttribute('opacity', stale ? '0.5' : '1');
      marker.querySelector('circle').setAttribute('fill', stale ? '#9ca8a1' : '#f5c665');
      label.textContent = (stale ? 'Stará poloha · ' : 'GPS · ') + age + ' s';
    }
  };
}());
