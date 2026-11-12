// URL-safe Base64 (RFC 4648 section 5), the form of the VAPID public key.

const BASE64_BLOCK_LENGTH = 4;
const PADDING = '=';
const URL_SAFE_PLUS = /-/g;
const URL_SAFE_SLASH = /_/g;

/** Decodes URL-safe Base64, with or without padding, to bytes. O(n). */
export const decodeBase64Url = (text: string): Uint8Array<ArrayBuffer> => {
  const paddingLength = (BASE64_BLOCK_LENGTH - (text.length % BASE64_BLOCK_LENGTH)) % BASE64_BLOCK_LENGTH;
  const base64 = text.replace(URL_SAFE_PLUS, '+').replace(URL_SAFE_SLASH, '/') + PADDING.repeat(paddingLength);
  const binary = atob(base64);

  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
};
