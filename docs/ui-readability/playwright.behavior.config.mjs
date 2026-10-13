import base from './playwright.config.mjs';
export default {
  ...base, testDir: '../../tests/e2e',
  testMatch: ['ui_redesign.spec.mjs', 'ui_typography.spec.mjs'],
  grepInvert: /actual route captures|actual before\/after capture matrix|CDP confirms/,
  outputDir: '/private/tmp/robot-scope-ui-readability-behavior',
};
