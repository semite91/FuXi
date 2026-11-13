import './word_content_music.less';

interface WordContentMusicProps {
  songTitle: string;
  artist: string;
  lyricsExcerpt: string;
  songUrl: string;
  linkLabel: string;
}

/** The excerpt is a q element, so the browser adds the quotes. The link opens in a new tab. */
const WordContentMusic = ({ songTitle, artist, lyricsExcerpt, songUrl, linkLabel }: WordContentMusicProps) => (
  <div className="word-content-music">
    <h3 className="word-content-music__title">{songTitle}</h3>
    <p className="word-content-music__artist">{artist}</p>
    <p className="word-content-music__excerpt">
      <q>{lyricsExcerpt}</q>
    </p>
    <a className="word-content-music__link" href={songUrl} target="_blank" rel="noopener noreferrer">
      {linkLabel}
    </a>
  </div>
);

export default WordContentMusic;
