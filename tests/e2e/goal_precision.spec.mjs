import { expect, test } from '@playwright/test';
import { installDashboardBackend } from './dashboard_backend.mjs';

test('success keeps real offset separate and never offers corrective motion', async ({ page }) => {
  const backend=await installDashboardBackend(page);
  backend.state.navigation.goal={state:'succeeded',goal_id:'1'.repeat(32),distance_remaining:0,
    precision_evidence:{goal_id:'1'.repeat(32), current:{fresh:true,frame_id:'map',body_frame_id:'base_link',stamp_ns:'1793188723000000000',age_s:.1,error:{xy_m:.308926,yaw_rad:-.472324}},
      result:{state:'succeeded',received_ros_ns:'1793188723000000000'}, stop:{confirmed_now:true}, precision:{satisfied_now:false}}};
  await page.goto('/#navigation');
  await expect(page.locator('#navigationGoalDistance')).toHaveText('0.00');
  await expect(page.locator('#navigationGoalMessage')).toContainText('Nav2 성공');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('XY 0.309 m');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('-27.06°');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('정지 확인: 현재 측정 확인');
  await expect(page.locator('#navigationGoalPrecision')).toContainText('충족: 미충족');
  expect(backend.state.requests.filter(r => r.path.includes('/navigation/goal'))).toEqual([]);
});

test('Navigation shows pending and rejected 3D refinement without enabling Goal', async ({ page }) => {
  const backend=await installDashboardBackend(page);
  backend.state.navigation.pipeline={state:'running',job_id:'1'.repeat(32)};
  backend.state.navigation.readiness.localization=false;
  backend.state.navigation.safety.can_send_goal=false;
  backend.state.navigation.operational_localization={fresh:true,ready:false,state:'INITIAL_REFINEMENT_CONFIRMING',metrics:{initial_confirmations:2}};
  await page.goto('/#navigation');
  await expect(page.locator('#navigationLocalizationState')).toHaveText('ALIGNING');
  await expect(page.locator('#navigationLocalizationNote')).toContainText('2/3');
  await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
  backend.state.navigation.operational_localization.state='CORRECTION_JUMP_RESEED_REQUIRED';
  await expect(page.locator('#navigationLocalizationState')).toHaveText('BLOCKED');
  await expect(page.locator('#navigationLocalizationNote')).toContainText('보정 한도 초과');
  await expect(page.locator('#navigationGoalPoseTool')).toBeDisabled();
  expect(backend.state.requests.filter(r => r.path.includes('/navigation/goal'))).toEqual([]);
});

test('Navigation initial pose uses the real URDF asset and never sends a pose just by dragging', async ({ page }) => {
  const backend=await installDashboardBackend(page);
  Object.assign(backend.state.navigation,{pipeline:{state:'running',job_id:'2'.repeat(32)},map:{id:backend.mapId,revision:backend.mapRevision}});
  backend.state.navigation.safety.can_set_initial_pose=true;
  await page.goto('/#navigation');
  await expect(page.locator('#navigationInitialPoseTool')).toBeEnabled();
  await page.evaluate(() => {
    const original=window.RobotScene3D.prototype.drawRobotMapPreview;
    window.mapModelDraws=[];
    window.RobotScene3D.prototype.drawRobotMapPreview=function(ctx,pose,project,...rest){
      const result=original.call(this,ctx,pose,project,...rest);
      if(result) window.mapModelDraws.push({pose:{...pose},model:this.getOfficialRobotModelStatus().model});
      return result;
    };
  });
  await page.locator('#navigationInitialPoseTool').click();
  const canvas=page.locator('#navigationMapCanvas');
  await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);
  await page.mouse.down();
  await page.mouse.move(box.x+box.width*.58,box.y+box.height*.43,{steps:5});
  await page.mouse.up();
  await expect.poll(()=>page.evaluate(()=>window.mapModelDraws.length)).toBeGreaterThan(0);
  await expect(page.locator('#navigationPoseCoordinates')).toContainText('URDF');
  await expect(page.locator('#navigationPoseSend')).toBeEnabled();
  const draw=await page.evaluate(()=>window.mapModelDraws.at(-1));
  expect(draw.pose.mode).toBe('initial');
  expect(draw.pose.yaw).toBeGreaterThan(0);
  expect(draw.model).toBeTruthy();
  expect(backend.state.requests.filter(r=>r.path.includes('/navigation/initial-pose')||r.path.includes('/navigation/goal'))).toEqual([]);
  await canvas.screenshot({path:'test-results/navigation-initial-urdf.png'});
  await page.locator('#navigationPoseDiscard').click();
  await expect(page.locator('#navigationPoseSend')).toBeDisabled();
});
