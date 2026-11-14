// Reads the stored Word Content string into the layout the back side shows.
// The engine stores JSON; an older Content is plain text and is shown as a story.

export type ParsedWordContent =
  | { kind: 'text'; title: string | null; content: string; sourceReference: string | null }
  | { kind: 'photo'; imageUrl: string }
  | { kind: 'music'; songTitle: string; artist: string; songUrl: string; lyricsExcerpt: string | null }
  | { kind: 'unavailable' };

type ContentFields = Record<string, unknown>;

const TEXT_METHODS: ReadonlySet<unknown> = new Set(['story', 'quote', 'film reference']);
const PHOTO_METHOD = 'photo';
const MUSIC_METHOD = 'music';
const FIELDS = {
  method: 'method',
  title: 'title',
  content: 'content',
  sourceReference: 'source_reference',
  imageUrl: 'image_url',
  songTitle: 'song_title',
  artist: 'artist',
  songUrl: 'song_url',
  lyricsExcerpt: 'lyrics_excerpt',
} as const;
const SECURE_PROTOCOL = 'https:';
// A Learner's own Drive image is stored by the engine as a JPEG data: URL; no other data: type is shown.
const DRIVE_IMAGE_PREFIX = 'data:image/jpeg;base64,';
const BASE64_PAYLOAD = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const UNAVAILABLE: ParsedWordContent = { kind: 'unavailable' };

/** The JSON object with a method, or null when the Content is an older plain text. */
const readFields = (stored: string): ContentFields | null => {
  let value: unknown;

  try {
    value = JSON.parse(stored);
  } catch {
    return null;
  }

  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null;
  }

  return FIELDS.method in value ? (value as ContentFields) : null;
};

const readText = (fields: ContentFields, name: string): string | null => {
  const value = fields[name];

  return typeof value === 'string' && value.trim() !== '' ? value : null;
};

/** Only an absolute https address can become an image or a link. */
const readSecureUrl = (fields: ContentFields, name: string): string | null => {
  const value = readText(fields, name);

  if (value === null) {
    return null;
  }

  try {
    const url = new URL(value);

    return url.protocol === SECURE_PROTOCOL ? url.href : null;
  } catch {
    return null;
  }
};

/** A JPEG data: URL with non-empty, valid standard Base64. O(n). */
const isDriveImageUrl = (value: string): boolean => {
  if (!value.startsWith(DRIVE_IMAGE_PREFIX)) {
    return false;
  }

  const payload = value.slice(DRIVE_IMAGE_PREFIX.length);

  return payload !== '' && BASE64_PAYLOAD.test(payload);
};

/** An image may also be a Drive JPEG; a song stays https only. */
const readImageUrl = (fields: ContentFields): string | null => {
  const value = readText(fields, FIELDS.imageUrl);

  return value !== null && isDriveImageUrl(value) ? value : readSecureUrl(fields, FIELDS.imageUrl);
};

const toText = (fields: ContentFields): ParsedWordContent => {
  const title = readText(fields, FIELDS.title);
  const content = readText(fields, FIELDS.content);

  return title === null || content === null
    ? UNAVAILABLE
    : { kind: 'text', title, content, sourceReference: readText(fields, FIELDS.sourceReference) };
};

const toPhoto = (fields: ContentFields): ParsedWordContent => {
  const imageUrl = readImageUrl(fields);

  return imageUrl === null ? UNAVAILABLE : { kind: 'photo', imageUrl };
};

/** The lyric excerpt is optional; a song without one is shown without a quote. */
const toMusic = (fields: ContentFields): ParsedWordContent => {
  const songTitle = readText(fields, FIELDS.songTitle);
  const artist = readText(fields, FIELDS.artist);
  const songUrl = readSecureUrl(fields, FIELDS.songUrl);
  const lyricsExcerpt = readText(fields, FIELDS.lyricsExcerpt);

  return songTitle === null || artist === null || songUrl === null
    ? UNAVAILABLE
    : { kind: 'music', songTitle, artist, songUrl, lyricsExcerpt };
};

export const parseWordContent = (stored: string): ParsedWordContent => {
  if (stored.trim() === '') {
    return UNAVAILABLE;
  }

  const fields = readFields(stored);

  if (fields === null) {
    return { kind: 'text', title: null, content: stored, sourceReference: null };
  }

  const method = fields[FIELDS.method];

  if (TEXT_METHODS.has(method)) {
    return toText(fields);
  }

  if (method === PHOTO_METHOD) {
    return toPhoto(fields);
  }

  return method === MUSIC_METHOD ? toMusic(fields) : UNAVAILABLE;
};
