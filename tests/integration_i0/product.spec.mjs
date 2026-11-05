import {test,expect} from '@playwright/test';

const state=page=>page.locator('[data-slot=status]');
async function select(page,names){for(const name of names){await page.getByRole('checkbox',{name:`Select ${name}`,exact:true}).check();await expect(state(page)).toContainText('previews ready');}}
async function save(page,name){
  await page.locator('[data-action=start]').click();await expect(state(page)).toContainText('SOLVED_CANDIDATE');
  await page.locator('[data-field=ack]').check();await page.locator('[data-action=accept]').click();await expect(state(page)).toContainText('ACCEPTED');
  await page.locator('[data-field=name]').fill(name);
  const receipt=page.waitForResponse(r=>r.url().endsWith('/exports')&&r.request().method()==='POST');
  await page.locator('[data-action=save]').click();const response=await receipt;expect(response.status()).toBe(201);
  const manifest=await response.json();expect(manifest.operational_installed).toBe(false);
  await expect(state(page)).toContainText('Saved and listed');return manifest;
}
test('product C2 SavedMapCatalog → actual D1/C1, two / three / incremental and ancestry refusal',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/extensions');await expect(state(page)).toContainText('Catalogue ready');
  await select(page,['map0','map1']);const ab=await save(page,'i0_browser_AB');expect(ab.point_count).toBe(800);
  await page.reload();await expect(state(page)).toContainText('Catalogue ready');await select(page,['map0','map1','map2']);
  const abc=await save(page,'i0_browser_ABC');expect(abc.point_count).toBe(1200);
  await page.reload();await expect(state(page)).toContainText('Catalogue ready');await select(page,['i0_browser_AB','map2']);
  const incremental=await save(page,'i0_browser_incremental');expect(incremental.point_count).toBe(1200);
  expect(Object.keys(incremental.provenance_dag).length).toBeGreaterThanOrEqual(3);
  await page.reload();await expect(state(page)).toContainText('Catalogue ready');await select(page,['i0_browser_AB','map0']);
  await page.locator('[data-action=start]').click();await expect(state(page)).toContainText('ANCESTRY_OVERLAP');
  await expect(page.locator('[data-action=accept]')).toBeDisabled();expect(errors).toEqual([]);
});
for(const width of [390,768,1440])for(const theme of ['dark','light'])test(`product scoped UI ${width}px ${theme}`,async({page},info)=>{
  await page.setViewportSize({width,height:1000});await page.goto('/extensions');
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  await expect(state(page)).toContainText('Catalogue ready');
  await expect(page.locator('.mmf')).toHaveAttribute('data-operator-usability','multimap');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect((await page.locator('[data-action=reload]').boundingBox()).height).toBeGreaterThanOrEqual(44);
  await page.locator('[data-feature=scene]').click();await expect(page.locator('.obstacle-scene')).toBeVisible();
  expect((await page.locator('[data-action=pause]').boundingBox()).height).toBeGreaterThanOrEqual(44);
  await page.locator('[data-action=pause]').focus();await page.keyboard.press('Enter');
  await expect(page.locator('[data-action=pause]')).toHaveAttribute('aria-pressed','true');
  await page.locator('[data-feature=replay]').click();await expect(page.locator('.rr-banner')).toContainText('REPLAY');
  expect(await page.locator('.os-overlay').count()).toBe(0);
  const contrast=await page.locator('.rr-note').evaluate(el=>{
    const luminance=color=>{const v=color.match(/[\d.]+/g).slice(0,3).map(n=>Number(n)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722;};
    const style=getComputedStyle(el),fg=luminance(style.color),bg=luminance(getComputedStyle(document.documentElement).backgroundColor);
    return (Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05);
  });expect(contrast).toBeGreaterThanOrEqual(4.5);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:info.outputPath(`product-${width}-${theme}.png`),fullPage:true});
  const longError='지도 사본의 원본 revision을 확인해 주세요. '+ 'a'.repeat(128);
  await page.route('**/api/v1/extensions/multimap/sources',route=>
    route.fulfill({status:409,json:{error:{code:'STALE_SOURCE_REVISION',message:longError}}}));
  await page.locator('[data-feature=multimap]').click();
  await expect(state(page)).toContainText(longError);
  expect(await page.locator('.mmf').evaluate(async el=>{
    const loaded=await document.fonts.load('14px "IBM Plex Sans KR"','지도');
    return loaded.length>0 && getComputedStyle(el).fontFamily.includes('IBM Plex')
      && document.documentElement.scrollWidth<=innerWidth+1;
  })).toBe(true);
});
test('actual C4/D2/D3 → C1 HTTP → mounted C3 expires while paused, no control writes',async({page,request})=>{
  const mutations=[];page.on('request',r=>{if(r.method()!=='GET')mutations.push(r.url());});
  await page.goto('/extensions');await page.locator('[data-feature=scene]').click();
  await expect(page.locator('.obstacle-scene')).toBeVisible();
  const seed=await request.post('/__i0_test__/frame',{headers:{Origin:'http://127.0.0.1:4191'}});expect(seed.status()).toBe(200);
  await expect(page.locator('.obstacle-scene')).toHaveAttribute('data-ready','true');
  await expect(page.locator('[data-testid=summary]')).toContainText('SYNTHETIC');
  await page.locator('[data-action=pause]').click();
  await expect(page.locator('[data-testid=risk]')).toContainText('UNKNOWN');
  await expect(page.locator('[data-testid=sources]')).not.toContainText('FRESH',{timeout:3000});
  await page.waitForTimeout(650);
  const wire=await request.get('/api/v1/extensions/scene/snapshot');expect((await wire.json()).obstacle_frame).toBeNull();
  await expect(page.locator('[data-testid=risk]')).toContainText('UNKNOWN');
  const health=await(await request.get('/__i0_test__/health')).json();expect(health.adapter_publications).toBe(0);expect(health.clearing).toBe('NOT_PROVEN');
  await page.locator('[data-feature=multimap]').click();expect(await page.locator('.os-overlay').count()).toBe(0);
  expect(mutations).toEqual([]);
});

test('installed parser → local picker → C3 replay / seek / compare; no uploads or control',async({page},info)=>{
  const {execFileSync}=await import('node:child_process');
  const {readFileSync}=await import('node:fs');
  const root=info.outputPath('private-inputs');
  execFileSync('python',['-m','tests.integration_i0.prepare_replays',root]);
  const errors=[],mutations=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()!=='GET')mutations.push(r.url());if(!r.url().startsWith('http://127.0.0.1:4191/'))external.push(r.url());});
  await page.goto('/extensions');await page.locator('[data-feature=replay]').click();
  await page.locator('input[data-run="0"]').setInputFiles(`${root}/review-0.json`);
  await expect(page.locator('.rr-precision')).toContainText('1793244679103000000');
  await expect(page.locator('.rr-precision')).toContainText('UNOBSERVED');
  await page.locator('input[data-run="1"]').setInputFiles(`${root}/review-1.json`);
  await expect(page.locator('.rr-comparison')).toContainText('동일 조건 A/B 아님');
  await page.getByRole('button',{name:'재생',exact:true}).click();
  await page.getByRole('button',{name:'일시정지',exact:true}).click();
  const clock=await page.locator('.rr-toolbar output').textContent();await page.waitForTimeout(100);
  expect(await page.locator('.rr-toolbar output').textContent()).toBe(clock);
  await page.locator('input[data-run="0"]').setInputFiles(`${root}/review-3.json`);
  await expect(page.locator('.rr-c3 [data-testid=summary]')).toContainText('REPLAY');
  await expect.poll(()=>page.locator('.os-overlay').evaluate(c=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).filter((v,i)=>i%4===3&&v>0).length)).toBeGreaterThan(0);
  const seek=page.getByRole('slider',{name:'재생 위치'});
  await seek.fill('1000');await seek.dispatchEvent('input');
  await expect(page.locator('.rr-c3 [data-testid=paths]')).not.toContainText('path-1');
  await seek.fill('0');await seek.dispatchEvent('input');
  await expect(page.locator('.rr-c3 [data-testid=paths]')).toContainText('path-1');
  await seek.fill('2000');await seek.dispatchEvent('input');
  await expect(page.locator('.rr-c3 [data-testid=paths]')).not.toContainText('path-1');
  await seek.fill('0');await seek.dispatchEvent('input');
  await page.screenshot({path:info.outputPath('replay-populated.png'),fullPage:true});
  const hostile=JSON.parse(readFileSync(`${root}/review-0.json`));
  hostile.provenance.source_id='<img src="https://invalid.example/x" onerror="window.i0xss=1">';
  await page.locator('input[data-run="0"]').setInputFiles({name:'untrusted.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(hostile))});
  await expect(page.locator('.rr-overview')).toContainText('<img');expect(await page.locator('.rr-overview img').count()).toBe(0);
  expect(await page.evaluate(()=>window.i0xss)).toBeUndefined();
  await page.locator('input[data-run="0"]').setInputFiles({name:'broken.json',mimeType:'application/json',buffer:Buffer.from('{')});
  await expect(page.locator('.rr-root')).toContainText('입력 차단');expect(await page.locator('.os-overlay').count()).toBe(0);
  await page.locator('[data-feature=multimap]').click();await page.locator('[data-feature=replay]').click();
  await expect(page.locator('.rr-events')).toBeEmpty();expect(await page.locator('.os-overlay').count()).toBe(0);
  expect(errors).toEqual([]);expect(mutations).toEqual([]);expect(external).toEqual([]);
});
