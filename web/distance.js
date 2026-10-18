'use strict';

// The viewer's location stays in this page's memory. It is never sent to the API.
window.ViewerDistance = (() => {
  const MAX_AGE = 60000;
  let position = null;
  let watch = null;
  let enabled = false;
  let generation = 0;
  let state = 'idle';
  let message = 'Use your location for an approximate straight-line distance. It stays in this browser.';
  const button = document.getElementById('distance-toggle');
  const status = document.getElementById('distance-status');

  function notify() {
    button.textContent = enabled ? 'Stop distance' : 'Show my distance';
    button.setAttribute('aria-pressed', String(enabled));
    status.textContent = message;
    window.dispatchEvent(new Event('viewerlocationchange'));
  }

  function stop() {
    generation++;
    if (watch !== null && navigator.geolocation) navigator.geolocation.clearWatch(watch);
    watch = null; enabled = false; position = null; state = 'idle';
    message = 'Use your location for an approximate straight-line distance. It stays in this browser.';
    notify();
  }

  function start() {
    if (!window.isSecureContext || !navigator.geolocation) {
      state = 'error';
      message = 'Your browser needs HTTPS to read your location. Localhost also works for testing; a plain Wi-Fi IP address does not.';
      notify(); return;
    }
    enabled = true; state = 'waiting'; position = null;
    message = 'Allow location access in this browser to measure your distance.';
    const current = ++generation;
    notify();
    try {
      const id = navigator.geolocation.watchPosition(fix => {
        if (generation !== current || !enabled) return;
        const {latitude, longitude, accuracy} = fix.coords;
        if (!validPoint(latitude, longitude) || !Number.isFinite(accuracy) || accuracy < 0 || !Number.isFinite(fix.timestamp)) return;
        position = {latitude, longitude, accuracy, timestamp: fix.timestamp};
        state = 'ready';
        message = 'Distance updates as you or the phone move. Your location stays in this browser.';
        notify();
      }, error => {
        if (generation !== current || !enabled) return;
        position = null; state = 'error';
        if (error.code === 1) {
          enabled = false;
          if (watch !== null) navigator.geolocation.clearWatch(watch);
          watch = null;
          message = 'Location permission was denied. Allow location in your browser’s site settings, then try again.';
        } else {
          message = error.code === 3 ? 'Your location timed out. Retrying while distance is enabled.' : 'Your location is unavailable. Keep device location on; the browser will retry.';
        }
        notify();
      }, {enableHighAccuracy: true, maximumAge: 15000, timeout: 15000});
      if (!enabled || generation !== current) navigator.geolocation.clearWatch(id);
      else watch = id;
    } catch (_) {
      enabled = false; state = 'error';
      message = 'The browser could not start location access. Check site permissions and try again.';
      notify();
    }
  }

  function validPoint(latitude, longitude) {
    return Number.isFinite(latitude) && Number.isFinite(longitude) && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
  }

  function distanceMetres(lat1, lon1, lat2, lon2) {
    if (!validPoint(lat1, lon1) || !validPoint(lat2, lon2)) return null;
    const radians = value => value * Math.PI / 180;
    const a = Math.sin(radians(lat2 - lat1) / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(radians(lon2 - lon1) / 2) ** 2;
    return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.max(0, Math.min(1, a))));
  }

  function currentPosition() {
    if (!position || Date.now() - position.timestamp > MAX_AGE || position.timestamp > Date.now() + 5000) return null;
    return position;
  }

  function directionsUrl(device) {
    if (!validPoint(device.latitude, device.longitude)) return null;
    const query = new URLSearchParams({api: '1', destination: `${device.latitude},${device.longitude}`});
    const viewer = currentPosition();
    // Opening the link shares these coordinates with Google Maps. There is no
    // route-service request while viewing or refreshing the dashboard.
    if (viewer) query.set('origin', `${viewer.latitude},${viewer.longitude}`);
    return `https://www.google.com/maps/dir/?${query}`;
  }

  function describe(device, live) {
    const label = live ? 'Distance from you' : 'Distance to last known position';
    if (!position) return {label, value: state === 'waiting' ? 'Locating you…' : state === 'error' ? 'Your location unavailable' : 'Enable your location', note: state === 'idle' ? 'Tap Show my distance above. Distance uses both devices’ locations.' : message};
    if (!currentPosition()) {
      return {label, value: 'Waiting for your current location', note: 'Your last location is too old to calculate a current distance.'};
    }
    const metres = distanceMetres(position.latitude, position.longitude, device.latitude, device.longitude);
    if (metres === null) return {label, value: 'Unavailable', note: 'Waiting for a valid phone location.'};
    const amount = metres < 1000 ? `${Math.round(metres).toLocaleString()} m` : `${(metres / 1000).toLocaleString(undefined, {maximumFractionDigits: metres < 100000 ? 1 : 0})} km`;
    return {label, value: `About ${amount}`, note: `Straight-line estimate · your accuracy ±${Math.round(position.accuracy).toLocaleString()} m; phone ±${Math.round(device.accuracy).toLocaleString()} m.`};
  }

  button.addEventListener('click', () => enabled ? stop() : start());
  return {describe, directionsUrl, distanceMetres, stop};
})();
