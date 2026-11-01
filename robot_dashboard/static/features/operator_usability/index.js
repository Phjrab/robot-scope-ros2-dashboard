// Explicit host opt-in. No state interpretation, observers, API calls, event
// listeners, canvas changes, focus moves or button activation.
const mounted = new WeakMap();
let nextGuide = 0;
export function mountOperatorUsability(root, surface) {
  const expected = { navigation: '[data-page="navigation"]', multimap: '.mmf', obstacles: '.obstacle-scene' };
  if (!expected[surface] || !root?.matches(expected[surface])) throw new TypeError('Matching feature root and surface required');
  if (mounted.has(root)) return mounted.get(root);
  const previousScope = root.getAttribute('data-operator-usability');
  root.setAttribute('data-operator-usability', surface);
  const descriptions = [];
  let guide;
  function describe(selector, ids) {
    const node = root.querySelector(selector);
    if (!node) return;
    const before = new Set((node.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    const added = ids.filter(id => !before.has(id) && root.ownerDocument.getElementById(id));
    node.setAttribute('aria-describedby', [...before, ...added].join(' '));
    descriptions.push({ node, added });
  }
  if (surface === 'navigation') {
    const toolbar = root.querySelector('.navigation-pose-toolbar');
    if (toolbar) {
      guide = root.ownerDocument.createElement('p');
      guide.className = 'ou-navigation-guide';
      do { guide.id = `ou-navigation-guide-${++nextGuide}`; } while (root.ownerDocument.getElementById(guide.id));
      guide.textContent = '지도 드래그는 초안입니다. SEND POSE 후 정합 완료를 확인하고, GOAL POSE → SEND GOAL 순서로 진행하세요.';
      toolbar.after(guide);
      describe('#navigationInitialPoseTool', [guide.id, 'navigationSafetyMessage']);
      describe('#navigationGoalPoseTool', [guide.id, 'navigationLocalizationState', 'navigationLocalizationNote', 'navigationSafetyMessage']);
      describe('#navigationPoseSend', [guide.id, 'navigationPoseCoordinates', 'navigationSafetyMessage']);
    }
  }
  if (surface === 'multimap') {
    const input = root.querySelector('[data-field="name"]');
    const toolbar = input?.closest('.mmf-toolbar');
    if (toolbar) {
      guide = root.ownerDocument.createElement('p');
      guide.className = 'mmf-note ou-name-guide';
      do { guide.id = `ou-name-guide-${++nextGuide}`; } while (root.ownerDocument.getElementById(guide.id));
      guide.textContent = '새 PCD 이름: 영문·숫자·_·-를 사용한 1–64자, 기존 지도와 다른 이름. 저장은 운영 지도 적용이 아닙니다.';
      toolbar.after(guide);
      describe('[data-field="name"]', [guide.id]);
      describe('[data-action="save"]', [guide.id]);
    }
  }
  const handle = { destroy() {
    if (mounted.get(root) !== handle) return;
    for (const {node, added} of descriptions) {
      const remaining = (node.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && !added.includes(id));
      if (remaining.length) node.setAttribute('aria-describedby', remaining.join(' '));
      else node.removeAttribute('aria-describedby');
    }
    guide?.remove();
    if (previousScope === null) root.removeAttribute('data-operator-usability');
    else root.setAttribute('data-operator-usability', previousScope);
    mounted.delete(root);
  } };
  mounted.set(root, handle);
  return handle;
}
