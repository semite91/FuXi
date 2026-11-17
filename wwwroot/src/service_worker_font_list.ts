// The build step that writes the built font files into public/service_worker.js (see vite.config.ts).
// The worker is plain JavaScript and cannot import this module, so it holds the same placeholder
// text; src/service_worker_font_list.test.ts checks that it does.
import type { Plugin } from 'vite';

export const SERVICE_WORKER_FILE = 'service_worker.js';
// Each marker stays in the built worker, so every build (also in watch mode) fills the value after it again.
export const FONT_CACHE_MARKER = '/* fuxi:font-cache */';
export const FONT_FILES_MARKER = '/* fuxi:font-files */';
// The values the dev server keeps: no font is cached there.
export const FONT_CACHE_PLACEHOLDER = `${FONT_CACHE_MARKER} 'fuxi-fonts-dev'`;
export const FONT_FILES_PLACEHOLDER = `${FONT_FILES_MARKER} []`;
export const FONT_CACHE_PREFIX = 'fuxi-fonts-';

const BUILT_FONT_FILE = /\.woff2$/;
// The value after a marker runs to the end of its statement.
const MARKED_VALUE = '[^;\\n]*';
const REGEX_SPECIAL = /[.*+?^${}()|[\]\\/]/g;
const ABSOLUTE_PATH = /^(?:[A-Za-z]:[\\/]|[\\/])/;
const BACKSLASH = /\\/g;
const TRAILING_SLASH = /\/+$/;
const FONT_CACHE_HASH_LENGTH = 8;
const HASH_ALGORITHM = 'SHA-256';
const HEX_RADIX = 16;
const HEX_BYTE_LENGTH = 2;
const TEXT_ENCODING = 'utf8';

const markedValue = (marker: string) => new RegExp(`${marker.replace(REGEX_SPECIAL, '\\$&')} ${MARKED_VALUE}`, 'g');

/** Puts a value after its marker. The marker must be there exactly once. */
const fillMarker = (worker: string, marker: string, value: unknown): string => {
  const pattern = markedValue(marker);
  const count = worker.match(pattern)?.length ?? 0;

  if (count !== 1) {
    throw new Error(`${SERVICE_WORKER_FILE} must hold ${marker} once; it holds it ${count} times.`);
  }

  // A function replacer, so $ sequences in the value are written as they are.
  const filled = `${marker} ${JSON.stringify(value)}`;

  return worker.replace(pattern, () => filled);
};

/** The worker with the cache name and font list of a build. A worker filled before is filled again. */
export const fillFontList = (worker: string, cacheName: string, fontUrls: readonly string[]): string =>
  fillMarker(fillMarker(worker, FONT_CACHE_MARKER, cacheName), FONT_FILES_MARKER, fontUrls);

/** The path of the built worker, for an output folder given relative to the root or as an absolute path. */
export const builtWorkerPath = (root: string, outDir: string): string => {
  const folder = ABSOLUTE_PATH.test(outDir) ? outDir : `${root}/${outDir}`;

  return `${folder.replace(BACKSLASH, '/').replace(TRAILING_SLASH, '')}/${SERVICE_WORKER_FILE}`;
};

/** A short hex hash of a text, by the Web Crypto API that Node has built in. */
const shortHash = async (text: string): Promise<string> => {
  const digest = await crypto.subtle.digest(HASH_ALGORITHM, new TextEncoder().encode(text));
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(HEX_RADIX).padStart(HEX_BYTE_LENGTH, '0')).join('');

  return hex.slice(0, FONT_CACHE_HASH_LENGTH);
};

/** The cache name of a build: a new set of fonts gives a new name. */
export const fontCacheName = async (fontUrls: readonly string[]): Promise<string> =>
  `${FONT_CACHE_PREFIX}${await shortHash(fontUrls.join('\n'))}`;

const MISSING_FILE_CODE = 'ENOENT';

const isMissingFile = (error: unknown) =>
  typeof error === 'object' && error !== null && (error as { code?: unknown }).code === MISSING_FILE_CODE;

/**
 * Writes the built font files and the cache name of the build into the built service worker,
 * so it caches every font on install. A failed build is left alone, and a build without the
 * worker in its output folder (no public files copied) is only warned about.
 */
export const fontPrecache = (): Plugin => {
  let base = '/';
  let workerPath = '';
  // Collected over every output of one build, so a second output adds its fonts instead of replacing them.
  const fontFiles = new Set<string>();

  return {
    name: 'fuxi-font-precache',
    apply: 'build',
    configResolved(config) {
      base = config.base;
      workerPath = builtWorkerPath(config.root, config.build.outDir);
    },
    // Each build (also each rebuild in watch mode) starts with an empty list.
    buildStart() {
      fontFiles.clear();
    },
    generateBundle(_options, bundle) {
      Object.keys(bundle)
        .filter((fileName) => BUILT_FONT_FILE.test(fileName))
        .forEach((fileName) => fontFiles.add(fileName));
    },
    // After the bundle and the public files are written, so the copied worker is there.
    async closeBundle(error) {
      if (error) {
        return;
      }

      let worker: string;
      try {
        worker = await this.fs.readFile(workerPath, { encoding: TEXT_ENCODING });
      } catch (readError) {
        if (!isMissingFile(readError)) {
          throw readError;
        }
        this.warn(`${SERVICE_WORKER_FILE} is not in the output folder, so its font list is not written.`);
        return;
      }

      const fontUrls = [...fontFiles].sort().map((fileName) => `${base}${fileName}`);
      const filled = fillFontList(worker, await fontCacheName(fontUrls), fontUrls);
      await this.fs.writeFile(workerPath, filled, { encoding: TEXT_ENCODING });
    },
  };
};
