'use strict';

// Keep one map per phone. Reusing it preserves zoom, panning and cached tiles
// when the dashboard receives its next location report.
window.PhoneMaps = (() => {
  const views = new Map();

  function create(device) {
    const frame = document.createElement('div');
    frame.className = 'map-frame';
    const toolbar = document.createElement('div');
    toolbar.className = 'map-toolbar';
    const label = document.createElement('span');
    const follow = document.createElement('button');
    follow.type = 'button'; follow.className = 'follow-phone'; follow.textContent = 'Follow phone';
    follow.setAttribute('aria-pressed', 'true');
    toolbar.append(label, follow);
    const canvas = document.createElement('div');
    canvas.className = 'phone-map';
    canvas.setAttribute('role', 'region');
    canvas.setAttribute('aria-label', `Location map for ${device.name}`);
    const message = document.createElement('p');
    message.className = 'map-message'; message.textContent = 'Loading street map…';
    message.setAttribute('role', 'status');
    frame.append(toolbar, canvas, message);
    const view = {frame, canvas, label, follow, message, map: null, following: true, device};
    views.set(device.id, view);
    return view;
  }

  function init(view) {
    if (!window.L) {
      view.message.textContent = 'The map could not load. You can still open the coordinates in Google Maps.';
      view.follow.disabled = true;
      return;
    }
    const device = view.device;
    const point = [device.latitude, device.longitude];
    view.map = L.map(view.canvas, {scrollWheelZoom: false, zoomControl: true}).setView(point, 16);
    view.tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, updateWhenIdle: true, keepBuffer: 1,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    });
    view.tiles.on('tileerror', () => {
      view.message.textContent = 'Street map unavailable. Check your internet connection; the location and Google Maps link are still available.';
      view.message.hidden = false;
    });
    view.tiles.on('tileload', () => { view.message.hidden = true; });
    view.tiles.addTo(view.map);
    view.accuracy = L.circle(point, {radius: device.accuracy, color: '#376e53', fillOpacity: .12, weight: 1.5}).addTo(view.map);
    view.marker = L.marker(point, {
      icon: L.divIcon({className: 'phone-map-pin', iconSize: [22, 22], iconAnchor: [11, 11]}),
      title: device.name, alt: 'Tracked phone location', keyboard: true,
    }).addTo(view.map);
    view.map.fitBounds(view.accuracy.getBounds(), {padding: [30, 30], maxZoom: 16, animate: false});
    view.map.on('dragstart', () => {
      view.following = false;
      view.follow.setAttribute('aria-pressed', 'false');
    });
    view.follow.addEventListener('click', () => {
      view.following = true;
      view.follow.setAttribute('aria-pressed', 'true');
      view.map.panTo([view.device.latitude, view.device.longitude], {animate: false});
    });
    view.latitude = device.latitude; view.longitude = device.longitude;
  }

  function update(view) {
    if (!view.map) return;
    const device = view.device;
    const point = [device.latitude, device.longitude];
    view.marker.setLatLng(point);
    view.marker.getElement()?.setAttribute('title', `${device.name}: ${device.latitude.toFixed(5)}, ${device.longitude.toFixed(5)}`);
    view.marker.getElement()?.classList.toggle('is-stale', !view.live);
    view.accuracy.setLatLng(point).setRadius(device.accuracy).setStyle({
      color: view.live ? '#376e53' : '#a37b39', dashArray: view.live ? null : '4 4',
    });
    if (view.following && (view.latitude !== device.latitude || view.longitude !== device.longitude)) {
      view.map.panTo(point, {animate: false});
    }
    view.latitude = device.latitude; view.longitude = device.longitude;
  }

  function render(device, live) {
    const view = views.get(device.id) || create(device);
    view.device = device; view.live = live;
    view.label.textContent = live ? 'Live location' : 'Last known position';
    view.frame.classList.toggle('map-stale', !live);
    // Maps need a visible, attached container before their first initialization.
    return view.frame;
  }

  function resize() {
    requestAnimationFrame(() => {
      for (const view of views.values()) {
        if (!view.canvas.isConnected) continue;
        if (!view.map) init(view);
        if (view.map) view.map.invalidateSize({pan: true, animate: false, debounceMoveend: true});
        update(view);
      }
    });
  }

  function retain(ids) {
    const keep = new Set(ids);
    for (const [id, view] of views) {
      if (!keep.has(id)) {
        if (view.map) view.map.remove();
        view.frame.remove(); views.delete(id);
      }
    }
  }

  window.addEventListener('resize', resize);
  window.addEventListener('online', () => {
    for (const view of views.values()) view.tiles?.redraw();
  });
  return {render, resize, retain, clear: () => retain([])};
})();
