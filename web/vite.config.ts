import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const apiTarget = (env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

  const createProxy = () => ({
    target: apiTarget,
    changeOrigin: true,
    configure: (proxy: {
      on: (
        event: string,
        handler: (...args: any[]) => void
      ) => void;
    }) => {
      proxy.on('proxyReq', (proxyReq: { removeHeader: (name: string) => void }) => {
        proxyReq.removeHeader('origin');
      });
      proxy.on(
        'error',
        (
          _err: unknown,
          _req: unknown,
          res: {
            headersSent?: boolean;
            writeHead: (status: number, headers: Record<string, string>) => void;
            end: (body: string) => void;
          }
        ) => {
          if (res && !res.headersSent) {
            res.writeHead(502, {
              'Content-Type': 'application/json',
              'X-Proxy-Backend-Down': '1',
            });
            res.end(
              JSON.stringify({
                detail: `Can't reach the backend at ${apiTarget}. Start it and retry.`,
              })
            );
          }
        }
      );
    },
  });

  return {
    plugins: [react()],
    server: {
      port: 3000,
      strictPort: true,
      proxy: {
        '/lessons': createProxy(),
        '/qc': createProxy(),
        '/health': createProxy(),
      },
    },
  };
});
