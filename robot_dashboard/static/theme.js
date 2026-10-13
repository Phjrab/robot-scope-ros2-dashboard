// UI preference only. Runs before styles to avoid flashing the wrong theme.
(() => {
  const key = 'robot-scope.ui.theme.v1';
  const root = document.documentElement;
  const valid = (value) => value === 'light' || value === 'dark';
  let theme = 'dark';
  try { const stored = localStorage.getItem(key); if (valid(stored)) theme = stored; } catch (_) {}

  function render() {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f4f7fa' : '#11161c');
    const button = document.getElementById('themeToggle');
    if (!button) return;
    const next = theme === 'dark' ? '화이트' : '다크';
    button.textContent = `${theme === 'dark' ? '☀' : '☾'} ${next} 모드`;
    button.setAttribute('aria-label', `${next} 모드로 전환`);
    button.setAttribute('aria-pressed', String(theme === 'light'));
    button.title = `현재 ${theme === 'light' ? '화이트' : '다크'} 모드 · ${next} 모드로 전환`;
  }
  render();
  document.addEventListener('DOMContentLoaded', () => {
    render();
    document.getElementById('themeToggle')?.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      render();
      try { localStorage.setItem(key, theme); } catch (_) {
        document.getElementById('themeToggle').title += ' · 저장 불가: 이 창에만 적용';
      }
    });
  }, { once: true });
  window.addEventListener('storage', (event) => {
    if (event.key !== key && event.key !== null) return;
    theme = valid(event.newValue) ? event.newValue : 'dark';
    render();
  });
})();
