import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  integrations: [react(), tailwind()],
  // Use GitHub Pages base when deploying to https://rob-foulkrod.github.io/ff/
  site: 'https://rob-foulkrod.github.io/ff',
  base: '/ff/',
  output: 'static',
  build: {
    format: 'directory'
  }
});
