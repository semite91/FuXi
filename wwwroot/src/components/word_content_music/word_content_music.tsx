import { Icon } from '../../image/icons';
import './word_content_music.less';

const ICON_SIZE = 16;
const NOTE_ICON_SIZE = 18;

// Spotify adds the edition to a title ("Here Comes The Sun - Remastered 2009"). The edition would not fit the one-line link.
const EDITION_SUFFIX = /\s+-\s+(?:\d{4}\s+)?(?:remaster(?:ed)?|live|mono|stereo|single version|radio edit|deluxe|version)\b.*$/i;

interface WordContentMusicProps {
  songTitle: string;
  artist: string;
  /** A song without an excerpt is shown without a quote. */
  lyricsExcerpt: string | null;
  songUrl: string;
}

/** The excerpt is a q element, so the browser adds the quotes. The whole line is the link and opens in a new tab. */
const WordContentMusic = ({ songTitle, artist, lyricsExcerpt, songUrl }: WordContentMusicProps) => (
  <div className="word-content-music">
    <a className="word-content-music__link" href={songUrl} target="_blank" rel="noopener noreferrer">
      <span className="word-content-music__note">
        <Icon name="music" size={NOTE_ICON_SIZE} />
      </span>
      <span className="word-content-music__text">
        <span className="word-content-music__title">{songTitle.replace(EDITION_SUFFIX, '')}</span>{' '}
        <span className="word-content-music__artist">{artist}</span>
      </span>
      <Icon name="external" size={ICON_SIZE} className="word-content-music__out" />
    </a>
    {lyricsExcerpt !== null && (
      <p className="word-content-music__excerpt">
        <q>{lyricsExcerpt}</q>
      </p>
    )}
  </div>
);

export default WordContentMusic;
