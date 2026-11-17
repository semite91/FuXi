// Phase 6a B12: the build step that writes the font list into the service worker.
import { expect, test, vi } from 'vitest';
import serviceWorkerCode from '../public/service_worker.js?raw';
import {
  FONT_CACHE_PLACEHOLDER,
  FONT_FILES_PLACEHOLDER,
  builtWorkerPath,
  fillFontList,
  fontCacheName,
  fontPrecache,
} from './service_worker_font_list';

const FIRST_FONTS = ['/assets/nunito-latin-500-normal-EugFkASW.woff2'];
const SECOND_FONTS = ['/assets/baloo-2-latin-800-normal-BbF3Etk1.woff2', '/assets/nunito-latin-500-normal-New12345.woff2'];

test('6a B12 public/service_worker.js holds the placeholders of the shared module once each', () => {
  expect(serviceWorkerCode.split(FONT_CACHE_PLACEHOLDER)).toHaveLength(2);
  expect(serviceWorkerCode.split(FONT_FILES_PLACEHOLDER)).toHaveLength(2);
});

test('6a B12 the fill writes the cache name and the font list after their markers', () => {
  const filled = fillFontList(serviceWorkerCode, 'fuxi-fonts-aaaaaaaa', FIRST_FONTS);

  expect(filled).toContain(`/* fuxi:font-cache */ "fuxi-fonts-aaaaaaaa";`);
  expect(filled).toContain(`/* fuxi:font-files */ ${JSON.stringify(FIRST_FONTS)};`);
  expect(filled).not.toContain(FONT_CACHE_PLACEHOLDER);
});

test('6a B12 a worker filled before is filled again (watch mode)', () => {
  const first = fillFontList(serviceWorkerCode, 'fuxi-fonts-aaaaaaaa', FIRST_FONTS);

  const second = fillFontList(first, 'fuxi-fonts-bbbbbbbb', SECOND_FONTS);

  expect(second).toBe(fillFontList(serviceWorkerCode, 'fuxi-fonts-bbbbbbbb', SECOND_FONTS));
  expect(second).not.toContain('fuxi-fonts-aaaaaaaa');
});

test('6a B12 a value holding $ sequences is written literally', () => {
  const fonts = ['/assets/a-$&-$1.woff2', "/assets/b-$'-$`.woff2"];

  const filled = fillFontList(serviceWorkerCode, 'fuxi-fonts-$&$1', fonts);

  expect(filled).toContain(`/* fuxi:font-cache */ "fuxi-fonts-$&$1";`);
  expect(filled).toContain(`/* fuxi:font-files */ ${JSON.stringify(fonts)};`);
});

test('6a B12 a worker without the markers fails the build', () => {
  expect(() => fillFontList('const FONT_FILES = [];', 'fuxi-fonts-aaaaaaaa', FIRST_FONTS)).toThrow();
});

test.each([
  ['a relative output folder', 'B:/app/wwwroot', 'dist', 'B:/app/wwwroot/dist/service_worker.js'],
  ['an absolute Windows output folder', 'B:/app/wwwroot', 'C:\\out\\fuxi\\', 'C:/out/fuxi/service_worker.js'],
  ['an absolute POSIX output folder', '/app/wwwroot', '/srv/fuxi', '/srv/fuxi/service_worker.js'],
])('6a B12 the worker is found for %s', (_, root, outDir, expected) => {
  expect(builtWorkerPath(root, outDir)).toBe(expected);
});

test('6a B12 the cache name changes with the font list', async () => {
  const first = await fontCacheName(FIRST_FONTS);

  expect(first).toMatch(/^fuxi-fonts-[0-9a-f]{8}$/);
  expect(await fontCacheName(FIRST_FONTS)).toBe(first);
  expect(await fontCacheName(SECOND_FONTS)).not.toBe(first);
});

const WORKER_PATH = 'B:/app/wwwroot/dist/service_worker.js';

const missingFileError = () => Object.assign(new Error('no such file'), { code: 'ENOENT' });

/** Runs the plugin's hooks as Vite does, over a fake output folder that holds one worker file (or none). */
const runPlugin = (hasWorker = true) => {
  const plugin = fontPrecache();
  const files = new Map<string, string>(hasWorker ? [[WORKER_PATH, serviceWorkerCode]] : []);
  const fs = {
    readFile: vi.fn(async (path: string) => {
      const file = files.get(path);
      if (file === undefined) {
        throw missingFileError();
      }
      return file;
    }),
    writeFile: vi.fn(async (path: string, data: string) => {
      files.set(path, data);
    }),
  };
  const warn = vi.fn();
  type Hook = (this: unknown, ...args: unknown[]) => unknown;
  const call = (name: 'configResolved' | 'buildStart' | 'generateBundle' | 'closeBundle', ...args: unknown[]) =>
    (plugin[name] as unknown as Hook).call({ fs, warn }, ...args);

  call('configResolved', { base: '/', root: 'B:/app/wwwroot', build: { outDir: 'dist' } });
  const bundleOf = (fontFiles: string[]) => Object.fromEntries(fontFiles.map((file) => [file.slice(1), {}]));
  /** One build; each list of fonts is one output of it. */
  const build = async (outputs: string[][], error?: Error) => {
    call('buildStart');
    outputs.forEach((fontFiles) => call('generateBundle', {}, bundleOf(fontFiles)));
    await call('closeBundle', error);
  };

  return { files, fs, warn, build };
};

test('6a B12 a failed build is left alone', async () => {
  const { fs, build } = runPlugin();

  await build([FIRST_FONTS], new Error('Build failed'));

  expect(fs.readFile).not.toHaveBeenCalled();
  expect(fs.writeFile).not.toHaveBeenCalled();
});

test('6a B12 each build writes its own font list into the built worker', async () => {
  const { files, build } = runPlugin();

  await build([FIRST_FONTS]);
  await build([SECOND_FONTS]);

  const worker = files.get(WORKER_PATH) ?? '';
  expect(worker).toContain(JSON.stringify([...SECOND_FONTS].sort()));
  expect(worker).toContain(JSON.stringify(await fontCacheName([...SECOND_FONTS].sort())));
  expect(worker).not.toContain(FIRST_FONTS[0]);
});

test('6a B12 a build with several outputs writes the fonts of every output', async () => {
  const { files, build } = runPlugin();

  await build([FIRST_FONTS, SECOND_FONTS]);

  const allFonts = [...FIRST_FONTS, ...SECOND_FONTS].sort();
  expect(files.get(WORKER_PATH)).toContain(JSON.stringify(allFonts));
});

test('6a B12 a build without the worker in its output folder warns and does not fail', async () => {
  const { fs, warn, build } = runPlugin(false);

  await expect(build([FIRST_FONTS])).resolves.toBeUndefined();

  expect(warn).toHaveBeenCalledTimes(1);
  expect(fs.writeFile).not.toHaveBeenCalled();
});
