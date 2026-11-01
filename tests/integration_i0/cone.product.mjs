import {test,expect} from '@playwright/test';
const status=p=>p.locator('[data-testid=cone-status]');
const toggle=p=>p.locator('[data-layer=cones]');
async function control(page,command){const r=await page.request.post('/__i0_test__/cone',{data:{command},headers:{Origin:'http://127.0.0.1:4192','x-i0-synthetic-fixture':'local-test-only'}});expect(r.ok()).toBe(true);}
async function pixels(page){return page.locator('.os-overlay').evaluate(c=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).filter((v,i)=>i%4===3&&v>0).length);}
test.beforeEach(async({page})=>{await page.goto('/');await control(page,'reset');});
for(const width of [390,820,1280,1440])for(const theme of ['dark','light'])test(`cone actual C1/C3 ${width}px ${theme}`,async({page},info)=>{
 const writes=[],external=[],errors=[];page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());if(!r.url().startsWith('http://127.0.0.1:4192/'))external.push(r.url());});page.on('pageerror',e=>errors.push(e.message));
 await page.setViewportSize({width,height:1000});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
 await expect(status(page)).toContainText('SIMULATED · VALID');await expect(toggle(page)).not.toBeChecked();expect(await pixels(page)).toBe(0);
 await toggle(page).check();await expect.poll(()=>pixels(page)).toBeGreaterThan(0);
 await expect(status(page)).toContainText('ISOLATED_DEMO_ONLY');await expect(status(page)).toContainText('HEIGHT_UNVERIFIED');
 await page.getByRole('button',{name:/cone-0 · traffic_cone/}).click();await expect(page.locator('[data-testid=inspector]')).toContainText('"radius_m": 0.1');
 await expect(page.locator('[data-testid=risk]')).toContainText('UNKNOWN');expect(await page.locator('.os-overlay').count()).toBe(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 const contrast=await status(page).evaluate(el=>{const lum=c=>{const v=c.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722;};const f=lum(getComputedStyle(el).color),b=lum(getComputedStyle(document.documentElement).backgroundColor);return(Math.max(f,b)+.05)/(Math.min(f,b)+.05);});expect(contrast).toBeGreaterThanOrEqual(4.5);
 await page.screenshot({path:info.outputPath(`cones-${width}-${theme}.png`),fullPage:true});
 await toggle(page).uncheck();await expect.poll(()=>pixels(page)).toBe(0);expect(writes).toEqual([]);expect(external).toEqual([]);expect(errors).toEqual([]);
});
test('stalled snapshot expires while paused, timeout visible, tab switch aborts and reopen has one overlay',async({page})=>{
 await expect(status(page)).toContainText('VALID');await toggle(page).check();
 await page.route('**/api/v1/extensions/scene/snapshot',()=>new Promise(()=>{}));
 await page.locator('[data-action=pause]').click();await expect(status(page)).toContainText('STALE',{timeout:2000});
 await expect.poll(()=>pixels(page)).toBe(0);await expect(page.locator('#expansion-status')).toContainText('REQUEST_TIMEOUT');
 await page.locator('[data-feature=replay]').click();await expect(page.locator('.os-overlay')).toHaveCount(0);
 await page.unrouteAll({behavior:'ignoreErrors'});await page.locator('[data-feature=scene]').click();
 await expect(status(page)).toContainText('VALID');await expect(page.locator('.os-overlay')).toHaveCount(1);await expect(toggle(page)).not.toBeChecked();
});
test('normal empty, stopped empty stale, foreign map generation and unavailable source remain distinct',async({page})=>{
 await control(page,'empty');await expect(status(page)).toContainText('VALID');await expect(status(page)).toContainText('0개');
 await control(page,'stop');await expect(status(page)).toContainText('STALE');
 await control(page,'reset');await expect(status(page)).toContainText('VALID');await toggle(page).check();await expect.poll(()=>pixels(page)).toBeGreaterThan(0);
 await control(page,'mismatch');await expect(page.locator('#expansion-status')).toContainText('C1_MAP_GENERATION_MISMATCH');await expect.poll(()=>pixels(page)).toBe(0);
 await control(page,'reset');await control(page,'unavailable');await expect(page.locator('#expansion-status')).toContainText('BLOCKED_INPUTS');
});
test('unauthorized C1 and absent legacy endpoint cannot bypass the host',async({browser})=>{
 const context=await browser.newContext();try{const response=await context.request.get('http://127.0.0.1:4192/api/v1/extensions/scene/snapshot');expect(response.status()).toBe(401);
 const legacy=await context.request.get('http://127.0.0.1:4192/api/v1/obstacles');expect(legacy.status()).toBe(404);}finally{await context.close();}
});
