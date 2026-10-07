import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const port = Number(process.env.PORT || 54154);
const types = { '.css': 'text/css; charset=utf-8', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.png': 'image/png' };
createServer((request, response) => {
  const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
  const requested = pathname === '/' ? 'inbox.html' : decodeURIComponent(pathname.slice(1));
  const target = normalize(join(root, requested));
  if (!target.startsWith(root) || !existsSync(target) || statSync(target).isDirectory()) { response.writeHead(404); response.end('Not found'); return; }
  response.writeHead(200, { 'Content-Type': types[extname(target)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  createReadStream(target).pipe(response);
}).listen(port, '127.0.0.1', () => console.log(`Local review: http://127.0.0.1:${port}/`));
