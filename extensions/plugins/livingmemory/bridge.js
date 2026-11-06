(() => {
  const context = {locale: 'zh-CN', language: 'zh', theme: 'dark', role: __ROLE__};
  async function call(path, method, data) {
    const url = new URL('/' + path.replace(/^\/+/, ''), location.origin);
    if (method === 'GET') Object.entries(data || {}).forEach(([k,v]) => url.searchParams.set(k,v));
    const response = await fetch(url, {method, credentials: 'same-origin',
      headers: {'Content-Type':'application/json'},
      body: method === 'POST' ? JSON.stringify(data || {}) : undefined});
    if (!response.ok) throw new Error('记忆服务请求失败：' + response.status);
    return response.json();
  }
  window.AstrBotPluginView = {
    ready: async () => context, getContext: () => context,
    onContext: fn => {fn(context); return () => {};},
    apiGet: (path, data) => call(path, 'GET', data),
    apiPost: (path, data) => call(path, 'POST', data)
  };
  history.replaceState(null, '', '/dashboard/');
  document.addEventListener('DOMContentLoaded', () => {document.title = context.role + ' · LivingMemory';});
})();
