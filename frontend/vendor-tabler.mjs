// Optional, explicit import of the real Tabler MIT CSS package. No remote code is
// executed by the browser; deployment uses locally vendored CSS behind strict CSP.
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const source = join(root, 'node_modules/@tabler/core/dist/css/tabler.min.css');
const targetDir = join(root, 'backend/app/static/vendor');
const target = join(targetDir,'tabler-core.css');
if (!existsSync(source)) {
  console.error('Tabler is not installed. Run npm install in the project root first.');
  process.exit(1);
}
mkdirSync(targetDir, {recursive:true});
copyFileSync(source,target);
const licensePaths = [
  join(root,'node_modules/@tabler/core/LICENSE'),
  join(root,'node_modules/@tabler/core/LICENSE.md')
];
const licenses = licensePaths.filter(existsSync);
if (licenses.length) writeFileSync(join(targetDir,'TABLER-LICENSE.txt'),readFileSync(licenses[0]));
console.log(`Installed Tabler 1.4.0 CSS locally at ${target}`);
console.log('All scripts remain the original TripParadox implementation.');
