import config from './playwright.ui-redesign.config.mjs';
export default { ...config, testMatch: 'ui_typography.spec.mjs', outputDir: '/private/tmp/robot-scope-typography-playwright-artifacts', timeout: 180_000 };
