// Rasterises the official Clerk SVGs (references/brand/*.svg) to transparent PNGs with Chrome.
// node tools/rasterize_logos.js   (needs playwright-core in node_modules or NODE_PATH; uses system Chrome)
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..');
const BRAND = path.join(ROOT, 'references', 'brand');
const OUT = path.join(ROOT, 'textures', 'brand');
fs.mkdirSync(OUT, { recursive: true });

// name -> [source svg, colour replacements, output width px]
const JOBS = {
  'logo_white': ['logotype-full-primary.svg', { '#131316': '#FFFFFF', '#6C47FF': '#FFFFFF', '#BAB1FF': '#FFFFFF' }, 3000],
  'logo_purple': ['logotype-full-primary.svg', { '#131316': '#6C47FF' }, 3000],
  'logo_primary': ['logotype-full-primary.svg', {}, 3000],
  'symbol_white': ['symbol-primary.svg', { '#6C47FF': '#FFFFFF', '#BAB1FF': '#FFFFFF' }, 1200],
  'symbol_primary': ['symbol-primary.svg', {}, 1200],
};

(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  for (const [name, [src, repl, width]] of Object.entries(JOBS)) {
    let svg = fs.readFileSync(path.join(BRAND, src), 'utf8');
    for (const [a, b] of Object.entries(repl)) svg = svg.split(a).join(b);
    const vb = /viewBox="0 0 (\d+) (\d+)"/.exec(svg);
    const w = +vb[1], h = +vb[2];
    const height = Math.round(width * h / w);
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    await page.setContent(`<html><body style="margin:0;background:transparent">${svg.replace('<svg ', `<svg style="width:${width}px;height:${height}px;display:block" `)}</body></html>`);
    await page.screenshot({ path: path.join(OUT, name + '.png'), omitBackground: true, clip: { x: 0, y: 0, width, height } });
    await page.close();
    console.log('wrote', name, width, height);
  }
  await browser.close();
})();
