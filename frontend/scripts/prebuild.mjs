/**
 * Writes public/_redirects for Netlify.
 * Set BACKEND_URL (e.g. https://dt-analyser-api.onrender.com) in Netlify env vars
 * so /api/* is proxied to the hosted FastAPI backend.
 */
import { writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const backend = process.env.BACKEND_URL?.replace(/\/$/, '');
const lines = [];

if (backend) {
  lines.push(`/api/*  ${backend}/api/:splat  200!`);
  console.log(`[prebuild] API proxy -> ${backend}/api/*`);
} else {
  console.warn('[prebuild] BACKEND_URL not set — /api will only work via VITE_API_BASE_URL or local dev proxy');
}

lines.push('/*  /index.html  200');
writeFileSync(join(root, 'public', '_redirects'), `${lines.join('\n')}\n`);
console.log('[prebuild] wrote public/_redirects');
