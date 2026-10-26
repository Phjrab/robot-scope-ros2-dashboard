// Server-owned replay through the existing loopback fixture. No path/model inputs.
export function createRGBReplayReview({container, document: doc}) {
  if (new URLSearchParams(globalThis.location?.search || '').get('rgb_review') !== '1') return null;
  const root = doc.createElement('div'), text = doc.createElement('pre');
  text.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:none;overflow:visible';
  root.dataset.rgbReview = 'true';
  const images = doc.createElement('div'); images.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px';
  root.append(text, images); container.append(root);
  let disposed = false, lastFrame = null, busy = false;
  return {
    async refresh() {
      if (busy || disposed) return;
      busy = true;
      try {
        const response = await fetch('/__fixture/rgb-review', {cache:'no-store'});
        if (!response.ok) throw new Error('전용 loopback replay 서버가 필요합니다.');
        const s = await response.json();
        if (disposed) return;
        if (!container.contains(root)) container.append(root);
        const o = s.observation, profile = s.profile, c = s.counts || {}, t = o?.timing;
        const ms = value => value == null ? '—' : (value * 1000).toFixed(1);
        const frame = o ? `${s.run_id}/${o.sequence}` : null;
        if (frame && lastFrame !== frame && !o.quality_flags?.includes('IMAGE_DECODE_FAILED')) {
          // Publish a matched pair atomically. One refresh and two image loads
          // at most; retain the previous pair if a bounded server frame expired.
          const pair = await Promise.all(['original', 'overlay'].map(kind => new Promise(resolve => {
            const img = doc.createElement('img');
            img.alt = kind === 'original' ? '저장 RGB 원본 · replay' : '검출 bbox와 raw 판정 · 출발 허가 아님';
            img.style.cssText = 'width:calc(50% - 6px);min-width:240px;max-width:100%;object-fit:contain';
            img.onload = () => resolve(img); img.onerror = () => resolve(null);
            img.src = `/__fixture/rgb-review/image/${frame}/${kind}`;
          })));
          if (disposed || pair.some(img => !img)) return;
          images.replaceChildren(...pair);
          images.dataset.frame = frame;
          lastFrame = frame;
        } else if (!frame || o.quality_flags?.includes('IMAGE_DECODE_FAILED')) {
          images.replaceChildren(); lastFrame = null; delete images.dataset.frame;
        }
        root.dataset.state = s.state; root.dataset.mode = s.mode || 'DISABLED';
        text.textContent = `저장 RGB 검토 · ${s.mode || 'DISABLED'} · LIVE 아님\n${s.state} · 처리 ${s.frames_processed || 0}장 · run ${s.run_id || '없음'}\n` +
          `재생 ${s.replay_mode || '—'} / ${s.clock_mode || '—'} · fixture 평가, 실시간 PASS 아님\n` +
          `입력 ${c.input || 0}/${s.input_frames || 0} · 처리 ${c.processed || 0} · coverage ${((s.coverage || 0)*100).toFixed(1)}% · decode 전 drop ${c.dropped_before_decode || 0} / 후 ${c.dropped_after_decode || 0}\n` +
          `pending 교체 ${c.replaced_pending || 0} · 표시 교체 ${c.replaced_display || 0} · invalid ${c.invalid || 0} · late result ${c.late_result || 0}\n` +
          `profile ${profile?.profile || '미선택'} · 해상도 ${profile?.imgsz || '—'} · NMS ${profile?.prediction_nms_iou ?? '—'}\n설정 SHA ${s.inference_settings_sha256 || '—'}\n` +
          `stage ${o?.stage || '없음'} · canonical raw ${o?.raw_state || 'UNKNOWN'} / stable ${o?.stable_state || 'UNKNOWN'}\n` +
          `검출 bbox: ${o?.detections?.map(d=>`${d.bbox_xyxy_native.join(',')} raw ${d.raw_state} (${d.stage})`).join(' / ') || '없음'}\n` +
          `UNKNOWN/차단: ${[o?.unknown_reason, ...(o?.quality_flags || []), ...(o?.projection_reasons || [])].filter(Boolean).join(', ') || '관측 대기'}\n` +
          `sequence ${o?.sequence ?? '—'} · stamp ${o?.source_stamp_ns || '—'} (${o?.source_clock || 'unknown'}) · 기록 offset ${o?.recorded_offset_s ?? '—'}s · 최초 receipt ${o?.first_received_s ?? '—'}\n` +
          `추론 ${ms(o?.inference_wall_s)}ms · pipeline ${ms(o?.pipeline_wall_s)}ms · 실제 pending ${ms(o?.worker_pending_s)}ms · encode ${ms(o?.encode_wall_s)}ms\n` +
          `schedule→처리 ${ms(o?.schedule_to_processing_s)}ms · schedule→게시 ${ms(o?.publish_lag_s)}ms (FIFO 길이 아님)\n` +
          `host monotonic: 예정 ${t?.scheduled_arrival_s ?? '—'} / decode ${t?.decode_started_s ?? '—'}→${t?.decode_completed_s ?? '—'} / enqueue ${t?.enqueued_s ?? '—'}\n` +
          `처리 시작 ${t?.processing_started_s ?? '—'} / 추론 완료 ${t?.inference_completed_s ?? '—'} / encode 완료 ${t?.encode_completed_s ?? '—'} / 게시 ${t?.published_s ?? '—'}\n` +
          `원본 기록 시계 미검증 · 설정 일치 ${o?.inference_binding_matches ?? '—'}\n앞발 / 물리 정지 / 경로 / 출발 증거: 제공 없음 · 출발 허가 없음\n` +
          `주의: raw GREEN은 출발 허가가 아닙니다. C4 과거 tile 검토: 표지판 false GREEN 3개, 근거 부족 housing 28개. 지연이 TTL 250ms를 넘을 수 있으며 실제 stable GREEN 정확도는 미승인입니다.\n${s.error || ''}`;
      } catch (error) { if (!disposed) text.textContent = error.message; }
      finally { busy = false; }
    },
    destroy() { disposed = true; root.remove(); },
  };
}
