import { readFileSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import StyleDictionary from 'style-dictionary';
import {
  cssFormat,
  jsonFlatFormat,
  jsonFormat,
  nativeFormat,
  tailwindCjs,
  tailwindDts,
  tailwindEsm,
  tailwindV4Css,
} from './lib/formats.mjs';
import { buildModel } from './lib/model.mjs';
import { previewHtml } from './lib/preview.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const { version } = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));

const formats = {
  'side/css': (m) => cssFormat(m),
  'side/tailwind-cjs': (m) => tailwindCjs(m),
  'side/tailwind-esm': (m) => tailwindEsm(m),
  'side/tailwind-dts': () => tailwindDts(),
  'side/tailwind-v4': (m) => tailwindV4Css(m),
  'side/react-native': (m) => nativeFormat(m),
  'side/json': (m) => jsonFormat(m, version),
  'side/json-flat': (m) => jsonFlatFormat(m),
  'side/preview': (m) => previewHtml(m, cssFormat(m), version),
};
for (const [name, render] of Object.entries(formats)) {
  StyleDictionary.registerFormat({ name, format: ({ dictionary }) => render(buildModel(dictionary.allTokens)) });
}

rmSync(resolve(root, 'dist'), { recursive: true, force: true });

const sd = new StyleDictionary({
  source: [resolve(root, 'tokens/base/**/*.json'), resolve(root, 'tokens/themes/**/*.json')],
  log: { verbosity: 'default' },
  platforms: {
    dist: {
      transforms: ['attribute/cti', 'name/kebab'],
      buildPath: `${resolve(root, 'dist')}/`,
      files: [
        { destination: 'css/side.css', format: 'side/css' },
        { destination: 'tailwind/preset.cjs', format: 'side/tailwind-cjs' },
        { destination: 'tailwind/preset.mjs', format: 'side/tailwind-esm' },
        { destination: 'tailwind/preset.d.ts', format: 'side/tailwind-dts' },
        { destination: 'tailwind/theme.css', format: 'side/tailwind-v4' },
        { destination: 'react-native/theme.ts', format: 'side/react-native' },
        { destination: 'json/tokens.json', format: 'side/json' },
        { destination: 'json/tokens.flat.json', format: 'side/json-flat' },
      ],
    },
    preview: {
      transforms: ['attribute/cti', 'name/kebab'],
      buildPath: `${resolve(root, 'preview')}/`,
      files: [{ destination: 'index.html', format: 'side/preview' }],
    },
  },
});

await sd.buildAllPlatforms();
