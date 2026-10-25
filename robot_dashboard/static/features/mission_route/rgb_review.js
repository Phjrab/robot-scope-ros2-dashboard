// Server-owned replay through the existing loopback fixture. No path/model inputs.
export function createRGBReplayReview({container, document: doc}) {
  if (new URLSearchParams(globalThis.location?.search || '').get('rgb_review') !== '1') return null;
  const root = doc.createElement('div'), text = doc.createElement('pre');
  root.dataset.rgbReview = 'true';
  const images = doc.createElement('div'); images.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px';
  const original = doc.createElement('img'), overlay = doc.createElement('img');
  original.alt = '저장 RGB 원본 · replay'; overlay.alt = '검출 bbox와 raw 판정 · 출발 허가 아님';
  for (const img of [original, overlay]) { img.style.cssText = 'width:calc(50% - 6px);min-width:240px;max-width:100%;object-fit:contain'; images.append(img); }
  root.append(text, images); container.append(root);
  let disposed = false, lastFrame = null;
  return {
    async refresh() {
      try {
        const response = await fetch('/__fixture/rgb-review', {cache:'no-store'});
        if (!response.ok) throw new Error('전용 loopback replay 서버가 필요합니다.');
        const s = await response.json();
        if (disposed) return;
        if (!container.contains(root)) container.append(root);
        const o = s.observation, profile = s.profile;
        root.dataset.state = s.state; root.dataset.mode = s.mode || 'DISABLED';
        text.textContent = `저장 RGB 검토 · ${s.mode || 'DISABLED'} · LIVE 아님\n${s.state} · 처리 ${s.frames_processed || 0}장 · run ${s.run_id || '없음'}\n` +
          `profile ${profile?.profile || '미선택'} · 해상도 ${profile?.imgsz || '—'} · NMS ${profile?.prediction_nms_iou ?? '—'}\n설정 SHA ${s.inference_settings_sha256 || '—'}\n` +
          `stage ${o?.stage || '없음'} · canonical raw ${o?.raw_state || 'UNKNOWN'} / stable ${o?.stable_state || 'UNKNOWN'}\n` +
          `검출 bbox: ${o?.detections?.map(d=>`${d.bbox_xyxy_native.join(',')} raw ${d.raw_state} (${d.stage})`).join(' / ') || '없음'}\n` +
          `UNKNOWN/차단: ${[o?.unknown_reason, ...(o?.quality_flags || []), ...(o?.projection_reasons || [])].filter(Boolean).join(', ') || '관측 대기'}\n` +
          `추론 ${o?.inference_wall_s == null ? '—' : (o.inference_wall_s*1000).toFixed(1)}ms · 처리 ${((o?.pipeline_wall_s || 0)*1000).toFixed(1)}ms · 대기 ${((o?.queue_residence_s || 0)*1000).toFixed(1)}ms\n` +
          `원본 기록 시계 미검증 · 설정 일치 ${o?.inference_binding_matches ?? '—'}\n앞발 / 물리 정지 / 경로 / 출발 증거: 제공 없음 · 출발 허가 없음\n` +
          `주의: raw GREEN은 출발 허가가 아닙니다. C4 과거 tile 검토: 표지판 false GREEN 3개, 근거 부족 housing 28개. 지연이 TTL 250ms를 넘을 수 있으며 실제 stable GREEN 정확도는 미승인입니다.\n${s.error || ''}`;
        if (o && lastFrame !== `${s.run_id}/${o.sequence}`) {
          lastFrame = `${s.run_id}/${o.sequence}`;
          original.src = `/__fixture/rgb-review/image/${lastFrame}/original`;
          overlay.src = `/__fixture/rgb-review/image/${lastFrame}/overlay`;
        }
      } catch (error) { if (!disposed) text.textContent = error.message; }
    },
    destroy() { disposed = true; root.remove(); },
  };
}
