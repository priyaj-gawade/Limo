import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { blobatar } from 'blobatar';
import {
  idle,
  happy,
  wink,
  sleepy,
  unsure,
  scared,
  smug,
  surprised,
  love,
  thinking
} from 'blobatar/expression';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outDir = path.resolve(__dirname, '../public/logos');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

// Mathematical continuous Apple squircle path for 512x512
const SQUIRCLE_PATH = 'M 0,256 C 0,55 55,0 256,0 C 457,0 512,55 512,256 C 512,457 457,512 256,512 C 55,512 0,457 0,256 Z';

// Color definitions for background themes
const PALETTES = [
  {
    key: 'white',
    name: 'Pure White Minimal',
    bgGrad: ['#ffffff', '#f1f5f9'],
    rimStroke: 'rgba(0, 0, 0, 0.09)',
    sheenOpacity: 0.0,
    shadowMultiplier: 0.35
  },
  {
    key: 'black',
    name: 'Obsidian Black',
    bgGrad: ['#181920', '#0a0b0e'],
    rimStroke: 'rgba(255, 255, 255, 0.16)',
    sheenOpacity: 0.08,
    shadowMultiplier: 1.2
  },
  {
    key: 'blue',
    name: 'Electric Cobalt Blue',
    bgGrad: ['#2563eb', '#1d4ed8'],
    rimStroke: 'rgba(255, 255, 255, 0.22)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'navy',
    name: 'Midnight Navy',
    bgGrad: ['#1e293b', '#0f172a'],
    rimStroke: 'rgba(255, 255, 255, 0.18)',
    sheenOpacity: 0.09,
    shadowMultiplier: 1.0
  },
  {
    key: 'sky',
    name: 'Vibrant Sky Blue',
    bgGrad: ['#0284c7', '#0369a1'],
    rimStroke: 'rgba(255, 255, 255, 0.20)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'purple',
    name: 'Modern Violet Purple',
    bgGrad: ['#8b5cf6', '#6d28d9'],
    rimStroke: 'rgba(255, 255, 255, 0.22)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'lavender',
    name: 'Pastel Lavender',
    bgGrad: ['#8c7ce0', '#725ec7'],
    rimStroke: 'rgba(255, 255, 255, 0.20)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'coral',
    name: 'Coral Rose',
    bgGrad: ['#f43f5e', '#be123c'],
    rimStroke: 'rgba(255, 255, 255, 0.22)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'terracotta',
    name: 'Warm Terracotta',
    bgGrad: ['#c95b3b', '#aa4325'],
    rimStroke: 'rgba(255, 255, 255, 0.18)',
    sheenOpacity: 0.09,
    shadowMultiplier: 0.85
  },
  {
    key: 'amber',
    name: 'Golden Amber Honey',
    bgGrad: ['#f59e0b', '#b45309'],
    rimStroke: 'rgba(255, 255, 255, 0.22)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'emerald',
    name: 'Emerald Mint',
    bgGrad: ['#10b981', '#047857'],
    rimStroke: 'rgba(255, 255, 255, 0.20)',
    sheenOpacity: 0.10,
    shadowMultiplier: 0.85
  },
  {
    key: 'sage',
    name: 'Matte Sage Green',
    bgGrad: ['#446754', '#2d483a'],
    rimStroke: 'rgba(255, 255, 255, 0.16)',
    sheenOpacity: 0.08,
    shadowMultiplier: 0.9
  },
  {
    key: 'slate',
    name: 'Slate Graphite',
    bgGrad: ['#475569', '#334155'],
    rimStroke: 'rgba(255, 255, 255, 0.16)',
    sheenOpacity: 0.08,
    shadowMultiplier: 1.0
  }
];

const LOGO_CONFIGS = [];

// 1. Generate TILTED WINK poses across all palettes
for (const p of PALETTES) {
  LOGO_CONFIGS.push({
    id: `limo_logo_tilted_${p.key}`,
    title: `Limo Logo - Tilted (${p.name})`,
    expression: wink,
    bgGrad: p.bgGrad,
    rimStroke: p.rimStroke,
    sheenOpacity: p.sheenOpacity,
    transform: 'translate(106, 135) rotate(12, 50, 50) scale(3.1)',
    shadow: { cx: 256, cy: 385, rx: 105, ry: 18, opacity: 0.38 * p.shadowMultiplier }
  });
}

// 2. Generate CORNER PEEKING UNSURE poses across all palettes
for (const p of PALETTES) {
  LOGO_CONFIGS.push({
    id: `limo_logo_peeking_${p.key}`,
    title: `Limo Logo - Corner Peeking (${p.name})`,
    expression: unsure,
    bgGrad: p.bgGrad,
    rimStroke: p.rimStroke,
    sheenOpacity: p.sheenOpacity,
    transform: 'translate(170, 185) rotate(-6, 50, 50) scale(4.2)',
    shadow: { cx: 380, cy: 450, rx: 120, ry: 24, opacity: 0.35 * p.shadowMultiplier }
  });
}

// Keep canonical names for backward compatibility
LOGO_CONFIGS.push(
  {
    id: 'limo_logo_sage_tilted',
    title: 'Limo Logo - Sage Green Tilted (Canonical)',
    expression: wink,
    bgGrad: ['#446754', '#2d483a'],
    rimStroke: 'rgba(255, 255, 255, 0.16)',
    sheenOpacity: 0.08,
    transform: 'translate(106, 135) rotate(12, 50, 50) scale(3.1)',
    shadow: { cx: 256, cy: 385, rx: 105, ry: 18, opacity: 0.38 }
  },
  {
    id: 'limo_logo_terracotta_peeking',
    title: 'Limo Logo - Terracotta Corner Peeking (Canonical)',
    expression: unsure,
    bgGrad: ['#c95b3b', '#aa4325'],
    rimStroke: 'rgba(255, 255, 255, 0.18)',
    sheenOpacity: 0.09,
    transform: 'translate(170, 185) rotate(-6, 50, 50) scale(4.2)',
    shadow: { cx: 380, cy: 450, rx: 120, ry: 24, opacity: 0.35 }
  },
  {
    id: 'limo_logo_dark_centered',
    title: 'Limo Logo - Obsidian Centered (Canonical)',
    expression: idle,
    bgGrad: ['#1c1d24', '#0f1014'],
    rimStroke: 'rgba(255, 255, 255, 0.16)',
    sheenOpacity: 0.08,
    transform: 'translate(106, 116) scale(3.0)',
    shadow: { cx: 256, cy: 375, rx: 110, ry: 20, opacity: 0.55 }
  },
  {
    id: 'limo_logo_macro_blue',
    title: 'Limo Logo - Electric Blue Macro Face',
    expression: surprised,
    bgGrad: ['#2563eb', '#1d4ed8'],
    rimStroke: 'rgba(255, 255, 255, 0.22)',
    sheenOpacity: 0.10,
    transform: 'translate(-40, 20) scale(5.9)',
    shadow: null
  },
  {
    id: 'limo_logo_lavender_sleepy',
    title: 'Limo Logo - Lavender Sleepy',
    expression: sleepy,
    bgGrad: ['#8c7ce0', '#725ec7'],
    rimStroke: 'rgba(255, 255, 255, 0.20)',
    sheenOpacity: 0.10,
    transform: 'translate(106, 120) scale(3.0)',
    shadow: { cx: 256, cy: 375, rx: 110, ry: 20, opacity: 0.32 }
  }
);

function buildSquircleSvg(cfg) {
  const rawSvg = blobatar('Limo', {
    hue: 225,
    traits: { shape: 0.65 },
    expression: cfg.expression
  });

  const innerMarkup = rawSvg
    .replace(/^<svg[^>]*>/, '')
    .replace(/<\/svg>$/, '');

  const gradId = `grad_${cfg.id}`;
  const clipId = `clip_${cfg.id}`;
  const blurId = `blur_${cfg.id}`;

  const shadowElement = cfg.shadow
    ? `<ellipse cx="${cfg.shadow.cx}" cy="${cfg.shadow.cy}" rx="${cfg.shadow.rx}" ry="${cfg.shadow.ry}" fill="#000000" opacity="${cfg.shadow.opacity.toFixed(3)}" filter="url(#${blurId})"/>`
    : '';

  const sheenElement = cfg.sheenOpacity > 0
    ? `<linearGradient id="sheen_${cfg.id}" x1="0%" y1="0%" x2="0%" y2="50%">
        <stop offset="0%" stop-color="#ffffff" stop-opacity="${cfg.sheenOpacity}"/>
        <stop offset="100%" stop-color="#ffffff" stop-opacity="0.0"/>
      </linearGradient>
      <path d="${SQUIRCLE_PATH}" fill="url(#sheen_${cfg.id})"/>`
    : '';

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="${gradId}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="${cfg.bgGrad[0]}"/>
      <stop offset="100%" stop-color="${cfg.bgGrad[1]}"/>
    </linearGradient>

    <!-- Mathematical Continuous Squircle Clip Path -->
    <clipPath id="${clipId}">
      <path d="${SQUIRCLE_PATH}"/>
    </clipPath>

    <!-- Gaussian Blur for Ground Contact Shadow -->
    <filter id="${blurId}" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="16"/>
    </filter>
  </defs>

  <!-- Squircle Base Tile -->
  <g clip-path="url(#${clipId})">
    <!-- Tile Background -->
    <path d="${SQUIRCLE_PATH}" fill="url(#${gradId})"/>

    <!-- Subtle Ambient Surface Sheen -->
    ${sheenElement}

    <!-- Contact Ground Shadow -->
    ${shadowElement}

    <!-- Pure Blobatar Mascot Character -->
    <g transform="${cfg.transform}">
      ${innerMarkup}
    </g>
  </g>

  <!-- Neo-skeuomorphic Rim Highlight -->
  <path d="${SQUIRCLE_PATH}" fill="none" stroke="${cfg.rimStroke}" stroke-width="2"/>
</svg>
`;
}

console.log(`Generating ${LOGO_CONFIGS.length} Limo SVG logos...`);
for (const cfg of LOGO_CONFIGS) {
  const svgContent = buildSquircleSvg(cfg);
  const svgPath = path.join(outDir, `${cfg.id}.svg`);
  fs.writeFileSync(svgPath, svgContent, 'utf-8');
}

fs.writeFileSync(
  path.join(outDir, 'manifest.json'),
  JSON.stringify(LOGO_CONFIGS.map(c => ({ id: c.id, title: c.title })), null, 2),
  'utf-8'
);

console.log(`Successfully generated ${LOGO_CONFIGS.length} SVG logos in ${outDir}`);
