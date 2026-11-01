import {defineConfig} from '@playwright/test';
import base from './playwright.i0.config.mjs';
export default defineConfig({...base,testMatch:'native.product.mjs'});
