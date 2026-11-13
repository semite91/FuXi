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

const toText = (fields: ContentFields): ParsedWordContent => {
  const title = readText(fields, FIELDS.title);
  const content = readText(fields, FIELDS.content);

  return title === null || content === null
    ? UNAVAILABLE
    : { kind: 'text', title, content, sourceReference: readText(fields, FIELDS.sourceReference) };
};

const toPhoto = (fields: ContentFields): ParsedWordContent => {
  const imageUrl = readSecureUrl(fields, FIELDS.imageUrl);

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
