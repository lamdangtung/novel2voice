import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

const appRoot = fileURLToPath(new URL('.', import.meta.url));
const appPort = Number(process.env.NOVEL2VOICE_APP_PORT || 8000);
const apiPort = Number(process.env.NOVEL2VOICE_API_PORT || 8001);

function localBoundary() {
  return {
    name: 'novel2voice-local-boundary',
    configureServer(server) {
      // Run before Vite's middleware: exact host + port, not broad localhost suffixes.
      server.middlewares.use((request, response, next) => {
        const hosts = [`127.0.0.1:${appPort}`, `localhost:${appPort}`];
        const origins = hosts.map(host => `http://${host}`);
        if (!hosts.includes(request.headers.host?.toLowerCase())) {
          response.statusCode = 400;
          return response.end('Invalid Host');
        }
        if (request.headers.origin && !origins.includes(request.headers.origin)) {
          response.statusCode = 403;
          return response.end('Invalid Origin');
        }
        let pathname;
        try { pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); }
        catch { response.statusCode = 400; return response.end('Invalid URL'); }
        const allowed = ['/', '/index.html'].includes(pathname)
          || ['/src/', '/node_modules/', '/@vite/', '/@id/', '/@fs/'].some(prefix => pathname.startsWith(prefix));
        const privateFile = pathname.split('/').some(part => part === '.git' || part === '.env' || part.startsWith('.env.'));
        const invalidSource = pathname.startsWith('/src/') && !/\.(vue|js|css|map)$/.test(pathname);
        if (!allowed || privateFile || invalidSource) {
          response.statusCode = 404;
          return response.end('Not found');
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [localBoundary(), vue(), tailwindcss()],
  define: {
    __VERIFICATION_MODE__: process.env.NOVEL2VOICE_VERIFICATION === '1',
    __API_ORIGIN__: JSON.stringify(process.env.VITE_API_ORIGIN || `http://127.0.0.1:${apiPort}`),
  },
  server: {
    host: '127.0.0.1', port: appPort, strictPort: true,
    allowedHosts: ['localhost'], cors: false,
    fs: { strict: true, allow: [appRoot], deny: ['.env', '.env.*', '**/.git/**', '**/*.pem'] },
    headers: {
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' http://127.0.0.1:${apiPort} http://localhost:${apiPort}; connect-src 'self' http://127.0.0.1:${apiPort} http://localhost:${apiPort} ws://127.0.0.1:${appPort} ws://localhost:${appPort}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`,
    },
  },
});
