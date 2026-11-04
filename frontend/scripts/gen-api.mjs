// Generates src/api/schema.d.ts from frontend/openapi.json (preferred) or
// VITE_API_BASE_URL/../openapi.json (live backend). Never hand-edit the output.
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let base = process.env.VITE_API_BASE_URL;
if (!base && existsSync(path.join(root, '.env.local'))) {
  const m = readFileSync(path.join(root, '.env.local'), 'utf8').match(/^VITE_API_BASE_URL=(.+)$/m);
  if (m) base = m[1].trim();
}
const saved = path.join(root, 'openapi.json');
const origin = (base ?? 'http://localhost:8000/api/v1').replace(/\/api\/v1\/?$/, '');
const source = existsSync(saved) ? saved : `${origin}/openapi.json`;
const out = path.join(root, 'src', 'api', 'schema.d.ts');
console.log(`gen:api  ${source} -> ${out}`);
const bin = path.join(root, 'node_modules', 'openapi-typescript', 'bin', 'cli.js');
execFileSync(process.execPath, [bin, source, '-o', out], { stdio: 'inherit' });
