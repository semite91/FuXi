// I5: the VAPID public key comes as URL-safe Base64 without padding.
import { expect, test } from 'vitest';
import { decodeBase64Url } from './base64_url';

test.each([
  ['no padding needed', 'AQID', [1, 2, 3]],
  ['one padding character', 'AQI', [1, 2]],
  ['two padding characters', 'AQ', [1]],
  ['"-" and "_" in place of "+" and "/"', '-_-_', [0xfb, 0xff, 0xbf]],
  ['an empty text', '', []],
])('decodes a text with %s', (_, text, bytes) => {
  expect(decodeBase64Url(text)).toEqual(new Uint8Array(bytes));
});

test('a 65-byte public key decodes to 65 bytes', () => {
  const key = 'B'.padEnd(87, 'A');

  expect(decodeBase64Url(key)).toHaveLength(65);
});
