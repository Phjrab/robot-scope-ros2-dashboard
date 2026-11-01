// Explicit local test: requires the SHA256-verified historical D3 archive, never ROS.
import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
test('historical native D3 parser output renders in the actual REPLAY product host',async({page},info)=>{
  const file=process.env.I0_NATIVE_REVIEW;
  if(!file)throw new Error('I0_NATIVE_REVIEW required: use documented SHA256-verified archive preparation');
  const run=JSON.parse(readFileSync(file));expect(run.mode).toBe('REPLAY');
  const errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url());});
  await page.goto('/extensions');await page.locator('[data-feature=replay]').click();
  await page.locator('input[data-run="0"]').setInputFiles(file);
  await expect(page.locator('.rr-overview')).toContainText('SIMULATION');
  const seek=page.getByRole('slider',{name:'재생 위치'});await seek.fill('4000');await seek.dispatchEvent('input');
  await expect(page.locator('.rr-c3 [data-testid=summary]')).toContainText('REPLAY');
  await expect.poll(()=>page.locator('.os-overlay').evaluate(c=>Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).filter((v,i)=>i%4===3&&v>0).length)).toBeGreaterThan(0);
  await page.screenshot({path:info.outputPath('historical-native-replay.png'),fullPage:true});
  expect(errors).toEqual([]);expect(writes).toEqual([]);
});
