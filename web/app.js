'use strict';
const $ = (id) => document.getElementById(id);
let creatingAccount = false;
let currentUser = null;
let devices = [];
let serverOffset = 0;
let disconnectId = null;
let activePair = null;
let refreshInProgress = false;
const deviceCards = new Map();

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`/api${path}`, {
      credentials: 'same-origin', cache: 'no-store', signal: controller.signal, ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.error || 'Something went wrong. Please try again.');
      error.status = response.status;
      throw error;
    }
    return result;
  } finally {
    clearTimeout(timeout);
  }
}

function errorAt(id, message) {
  $(id).textContent = message || '';
  $(id).hidden = !message;
}

function showAuth() {
  window.PhoneMaps?.clear();
  deviceCards.clear();
  $('devices').replaceChildren();
  currentUser = null;
  devices = [];
  window.ViewerDistance?.stop();
  activePair = null;
  $('pair-code').value = '';
  $('password').value = '';
  setAuthMode(false);
  $('loading').hidden = true;
  $('dashboard').hidden = true;
  $('logout').hidden = true;
  $('auth-view').hidden = false;
  $('pair-dialog').close();
  $('disconnect-dialog').close();
}

async function showDashboard(user) {
  currentUser = user;
  $('auth-view').hidden = true;
  $('loading').hidden = true;
  $('dashboard').hidden = false;
  $('logout').hidden = false;
  $('account-label').textContent = `Signed in as ${user.username}`;
  await refresh();
}

function setAuthMode(create) {
  creatingAccount = create;
  $('auth-title').textContent = creatingAccount ? 'Make yourself at home.' : 'Welcome back.';
  $('auth-description').textContent = creatingAccount ? 'Create your account, then connect your Android phone. Choose a password you can keep safe.' : 'Sign in with an account you already created. New here? Choose Create an account below.';
  $('auth-submit').replaceChildren(document.createTextNode(creatingAccount ? 'Create account' : 'Sign in'), arrow('↗'));
  $('auth-switch-label').textContent = creatingAccount ? 'Already have an account?' : 'First time here?';
  $('auth-switch').textContent = creatingAccount ? 'Sign in' : 'Create an account';
  $('password').autocomplete = creatingAccount ? 'new-password' : 'current-password';
  $('password').value = '';
  $('confirm-password').value = '';
  $('confirm-password-field').hidden = !creatingAccount;
  $('confirm-password').disabled = !creatingAccount;
  $('confirm-password').required = creatingAccount;
  errorAt('auth-error', '');
}
$('auth-switch').addEventListener('click', () => setAuthMode(!creatingAccount));

function arrow(value) {
  const el = document.createElement('span');
  el.setAttribute('aria-hidden', 'true');
  el.textContent = value;
  return el;
}

$('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  errorAt('auth-error', '');
  if (creatingAccount && $('password').value !== $('confirm-password').value) {
    errorAt('auth-error', 'Passwords do not match. Enter the same password twice.');
    $('confirm-password').focus();
    return;
  }
  $('auth-submit').disabled = true;
  $('auth-switch').disabled = true;
  try {
    const credentials = {username: $('username').value, password: $('password').value};
    await api(creatingAccount ? '/register' : '/login', {method: 'POST', body: JSON.stringify(credentials)});
    $('password').value = '';
    $('confirm-password').value = '';
    await showDashboard(await api('/me'));
  } catch (error) { errorAt('auth-error', error.message); }
  finally { $('auth-submit').disabled = false; $('auth-switch').disabled = false; }
});

$('logout').addEventListener('click', async () => {
  try {
    await api('/logout', {method: 'POST', body: '{}'});
    showAuth();
  } catch (error) { errorAt('dashboard-error', error.message); }
});

function openPair() {
  activePair = null;
  $('pair-form').reset();
  $('pair-form').hidden = false;
  $('pair-details').hidden = true;
  errorAt('pair-error', '');
  $('pair-dialog').showModal();
}
$('add-phone').addEventListener('click', openPair);
$('empty-add').addEventListener('click', openPair);
$('close-pair').addEventListener('click', () => $('pair-dialog').close());

function showPairServerAddress(address) {
  const host = new URL(address).hostname;
  const localOnly = host === 'localhost' || host.endsWith('.localhost') || /^127\./.test(host) || ['0.0.0.0', '[::1]', '[::]'].includes(host);
  $('server-address').value = localOnly ? '' : address;
  $('server-address').placeholder = localOnly ? 'Use your computer’s Wi-Fi IP or hosted HTTPS address' : '';
  $('copy-server-address').disabled = localOnly;
  $('server-address-note').textContent = localOnly
    ? 'This page was opened on this computer only. Localhost on a phone points to the phone. Open this dashboard using your computer’s Wi-Fi IP (same Wi-Fi) or your hosted HTTPS address before copying the server address.'
    : 'Enter this exact address in the Android app. For a local Wi-Fi address, keep both devices on the same Wi-Fi and the computer’s server running.';
}

$('pair-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('create-code').disabled = true;
  errorAt('pair-error', '');
  try {
    activePair = await api('/devices', {method: 'POST', body: JSON.stringify({name: $('phone-name').value})});
    $('pair-form').hidden = true;
    $('pair-details').hidden = false;
    showPairServerAddress(activePair.server_url);
    $('pair-code').value = activePair.code.match(/.{1,4}/g).join('-');
    updatePairTime();
    await refresh();
  } catch (error) { errorAt('pair-error', error.message); }
  finally { $('create-code').disabled = false; }
});

function now() { return Date.now() / 1000 + serverOffset; }
function updatePairTime() {
  if (!activePair || !$('pair-dialog').open) return;
  const remaining = Math.ceil(activePair.expires_at - now());
  $('pair-expiry').textContent = remaining > 0 ? `One use only · Expires in ${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')}` : 'Code expired. Close this window, disconnect the pending phone, and create a new code.';
}

document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const input = $(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(input.value);
      button.textContent = 'Copied';
      setTimeout(() => button.textContent = 'Copy', 1800);
    } catch (_) {
      input.focus(); input.select(); button.textContent = 'Select & copy';
    }
  });
});

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function ago(stamp) {
  if (!stamp) return 'Not yet';
  const seconds = Math.max(0, Math.floor(now() - stamp));
  if (seconds < 5) return 'Just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return new Date(stamp * 1000).toLocaleDateString();
}

function renderDevices() {
  const container = $('devices');
  const visibleIds = new Set(devices.map(device => device.id));
  for (const [id, card] of deviceCards) {
    if (!visibleIds.has(id)) { card.remove(); deviceCards.delete(id); }
  }
  let cardIndex = 0;
  for (const device of devices) {
    const hasFix = device.latitude !== null && device.longitude !== null;
    const online = device.seen_at && now() - device.seen_at < 60;
    const fresh = hasFix && now() - device.located_at < 60;
    const live = device.tracking && online && fresh;
    let badgeText = live ? 'Live' : hasFix ? 'Last known' : device.paired_at ? 'Waiting for location' : 'Awaiting pairing';
    if (!device.tracking && device.seen_at) badgeText = 'Sharing stopped';
    let card = deviceCards.get(device.id);
    if (!card) {
      card = element('article', 'device-card');
      deviceCards.set(device.id, card);
      container.append(card);
    }
    // Keep the map and its parent connected during polling. Detaching a live
    // image grid can interrupt pending street tiles or a zoom gesture.
    const mapFrame = hasFix ? card.querySelector('.map-frame') : null;
    for (const child of Array.from(card.children)) {
      if (child !== mapFrame) child.remove();
    }
    const top = element('div', 'device-top');
    const identity = element('div', 'device-identity');
    const icon = element('div', 'device-icon', '⌖'); icon.setAttribute('aria-hidden', 'true');
    const title = element('div');
    title.append(element('h2', 'device-name', device.name), element('p', 'device-subtitle', device.paired_at ? 'Connected Android phone' : 'Connect in the Android app'));
    identity.append(icon, title);
    const badge = element('span', `badge ${live ? 'live' : hasFix ? 'stale' : 'waiting'}`);
    if (live) badge.append(element('span', 'status-dot'));
    badge.append(document.createTextNode(badgeText));
    top.append(identity, badge); card.insertBefore(top, mapFrame);
    if (hasFix) {
      if (window.PhoneMaps) {
        const map = PhoneMaps.render(device, live);
        if (map.parentNode !== card) card.append(map);
      }
      const panel = element('div', 'location-panel');
      panel.append(element('p', 'eyebrow', live ? 'LATEST LOCATION' : 'LAST KNOWN LOCATION'));
      panel.append(element('p', 'coordinates', `${device.latitude.toFixed(5)}, ${device.longitude.toFixed(5)}`));
      const stamp = element('p', 'location-caption', `Location captured ${ago(device.located_at)}`);
      stamp.title = new Date(device.located_at * 1000).toLocaleString();
      panel.append(stamp); card.append(panel);
      const details = element('div', 'location-details');
      for (const [label, value] of [['Accuracy', `± ${Math.round(device.accuracy).toLocaleString()} m`], ['Phone last seen', ago(device.seen_at)], ['Battery', device.battery === null ? '—' : `${device.battery}%`]]) {
        const detail = element('div'); detail.append(element('span', 'detail-label', label), element('span', 'detail-value', value)); details.append(detail);
      }
      card.append(details);
      if (window.ViewerDistance) {
        const distance = ViewerDistance.describe(device, live);
        const box = element('div', 'distance-panel');
        box.append(element('p', 'detail-label distance-label', distance.label), element('p', 'distance-value', distance.value), element('p', 'distance-note', distance.note));
        const directions = element('a', 'directions-link', live ? 'Route & travel time in Google Maps ↗' : 'Route to last known position in Google Maps ↗');
        directions.href = ViewerDistance.directionsUrl(device);
        directions.target = '_blank'; directions.rel = 'noopener noreferrer';
        // Recheck at activation too: a tab may have been hidden long enough
        // for the viewer fix to expire since the link was last rendered.
        for (const event of ['click', 'auxclick', 'contextmenu']) {
          directions.addEventListener(event, () => { directions.href = ViewerDistance.directionsUrl(device); });
        }
        box.append(directions, element('p', 'distance-note route-note', 'See route distance and estimated travel time; choose walking or driving in Google Maps. Opening directions shares the destination and your starting position, if enabled, with Google.'));
        card.append(box);
      }
    } else {
      card.append(element('p', 'pending-copy', device.paired_at ? 'Your phone is connected. Open the Android app, allow location access, and tap Start tracking. The first GPS fix can take a moment outdoors.' : device.pairing_expires > now() ? 'Enter the pairing code in your Android app. Codes expire after 10 minutes. If you closed the code window, disconnect this entry and create a new one.' : 'This pairing code has expired. Disconnect this entry and create a new one to try again.'));
    }
    const bottom = element('div', 'device-bottom');
    if (hasFix) {
      const maps = element('a', '', 'Open in Google Maps ↗');
      maps.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${device.latitude},${device.longitude}`)}`;
      maps.target = '_blank'; maps.rel = 'noopener noreferrer'; bottom.append(maps);
    } else bottom.append(element('span', 'device-subtitle', device.paired_at ? 'Waiting for first update' : 'Pair before starting tracking'));
    const disconnect = element('button', 'disconnect', 'Disconnect');
    disconnect.addEventListener('click', () => {
      disconnectId = device.id;
      errorAt('disconnect-error', '');
      $('disconnect-dialog').showModal();
    });
    bottom.append(disconnect); card.append(bottom);
    if (container.children[cardIndex] !== card) container.insertBefore(card, container.children[cardIndex] || null);
    cardIndex++;
  }
  if (window.PhoneMaps) {
    PhoneMaps.retain(devices.filter(d => d.latitude !== null && d.longitude !== null).map(d => d.id));
    PhoneMaps.resize();
  }
  $('empty-state').hidden = devices.length !== 0;
}

$('cancel-disconnect').addEventListener('click', () => $('disconnect-dialog').close());
$('confirm-disconnect').addEventListener('click', async () => {
  if (!disconnectId) return;
  $('confirm-disconnect').disabled = true;
  try {
    await api(`/devices/${disconnectId}`, {method: 'DELETE'});
    $('disconnect-dialog').close(); disconnectId = null;
    await refresh();
  } catch (error) { errorAt('disconnect-error', error.message); }
  finally { $('confirm-disconnect').disabled = false; }
});

async function refresh() {
  if (!currentUser || refreshInProgress) return;
  const requestedUser = currentUser;
  refreshInProgress = true;
  try {
    const result = await api('/devices');
    if (currentUser !== requestedUser) return;
    serverOffset = result.server_time - Date.now() / 1000;
    devices = result.devices;
    renderDevices();
    $('connection-status').replaceChildren(element('span', 'status-dot'), document.createTextNode('Dashboard connected · refreshes every 5s'));
    errorAt('dashboard-error', '');
    if (activePair && devices.some(d => d.id === activePair.id && d.paired_at)) {
      $('pair-dialog').close(); activePair = null;
    }
  } catch (error) {
    if (currentUser !== requestedUser) return;
    if (error.status === 401) { showAuth(); return; }
    $('connection-status').replaceChildren(element('span', 'status-dot offline'), document.createTextNode('Connection lost · retrying'));
    errorAt('dashboard-error', 'Cannot reach the server. Displayed locations may be out of date. Reconnecting automatically.');
    renderDevices();
  } finally { refreshInProgress = false; }
}

setInterval(() => { if (!document.hidden) refresh(); }, 5000);
setInterval(updatePairTime, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
window.addEventListener('online', refresh);
window.addEventListener('viewerlocationchange', () => { if (currentUser) renderDevices(); });
api('/me').then(showDashboard).catch(error => {
  showAuth();
  if (error.status !== 401) errorAt('auth-error', 'Cannot reach the server. Check your connection and reload.');
});
