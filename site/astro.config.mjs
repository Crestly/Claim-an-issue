import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import { SITE_URL } from './src/config.ts';

export default defineConfig({
  site: SITE_URL,
  output: 'static',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  integrations: [
    sitemap({
      // Pages without real data are excluded from the sitemap and carry noindex.
      filter: (page) => !page.includes('/_') && !page.endsWith('/404/'),
    }),
  ],
  vite: {
    build: { assetsInlineLimit: 0 },
  },
});
