import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  integrations: [react(), tailwind()],
  site: 'https://foulknfootball.com',
  base: '/',
  output: 'static',
  build: {
    format: 'directory'
  }
});