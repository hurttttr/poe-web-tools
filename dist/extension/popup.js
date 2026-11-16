(function () {
  'use strict';

  var SITES = {
    fb: {
      url: 'https://www.filterblade.xyz/?game=Poe1',
      match: 'filterblade.xyz'
    },
    ninja: {
      url: 'https://poe.ninja/poe1/economy',
      match: 'poe.ninja'
    },
    planner: {
      url: 'https://poeplanner.com/atlas-tree',
      match: 'poeplanner.com'
    }
  };

  var currentTabId = null;

  function send(msg, cb) {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs || !tabs[0]) { if (cb) cb(null); return; }
      currentTabId = tabs[0].id;
      chrome.tabs.sendMessage(tabs[0].id, Object.assign({ channel: 'fbzh' }, msg), function (res) {
        if (cb) cb(chrome.runtime.lastError ? null : res);
      });
    });
  }

  function render(s) {
    var stat = document.getElementById('stat');
    if (!s) {
      stat.textContent = '当前标签不是受支持的站点，可从上方卡片跳转';
      return;
    }
    document.getElementById('enabled').checked = s.enabled;
    document.querySelectorAll('.seg button').forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === s.mode);
    });
    stat.textContent = '词条 ' + s.entries.toLocaleString() + ' 条 · 已翻译 ' +
      s.stats.nodes + ' 处文本 / ' + s.stats.attributes + ' 处提示';
  }

  // 站点跳转：默认新标签打开，勾选后在当前标签跳转
  function markCurrent(url) {
    Object.keys(SITES).forEach(function (key) {
      var btn = document.getElementById('site-' + key);
      var isCurrent = url && url.indexOf(SITES[key].match) >= 0;
      btn.classList.toggle('current', !!isCurrent);
      var old = btn.querySelector('.badge');
      if (old) old.remove();
      if (isCurrent) {
        var badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = '当前';
        btn.appendChild(badge);
      }
    });
  }

  function openSite(key) {
    var url = SITES[key].url;
    var inCurrent = document.getElementById('same-tab').checked;
    if (inCurrent && currentTabId !== null) chrome.tabs.update(currentTabId, { url: url });
    else chrome.tabs.create({ url: url });
    window.close();
  }

  document.getElementById('site-fb').addEventListener('click', function () { openSite('fb'); });
  document.getElementById('site-ninja').addEventListener('click', function () { openSite('ninja'); });
  document.getElementById('site-planner').addEventListener('click', function () { openSite('planner'); });

  document.getElementById('enabled').addEventListener('change', function (e) {
    send({ type: 'set', patch: { enabled: e.target.checked } }, render);
  });
  document.querySelectorAll('.seg button').forEach(function (b) {
    b.addEventListener('click', function () {
      send({ type: 'set', patch: { mode: b.dataset.mode } }, render);
    });
  });
  document.getElementById('refresh').addEventListener('click', function () {
    send({ type: 'retranslate' }, render);
  });
  document.getElementById('export').addEventListener('click', function () {
    send({ type: 'export' });
  });

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs && tabs[0]) {
      currentTabId = tabs[0].id;
      markCurrent(tabs[0].url || '');
    }
  });
  send({ type: 'status' }, render);
})();
