import './word_content_picture.less';

interface WordContentPictureProps {
  imageUrl: string;
  /** The Word's name. */
  alt: string;
  /** Called when the picture cannot be loaded. */
  onError: () => void;
}

const WordContentPicture = ({ imageUrl, alt, onError }: WordContentPictureProps) => (
  <img
    className="word-content-picture"
    src={imageUrl}
    alt={alt}
    loading="lazy"
    decoding="async"
    referrerPolicy="no-referrer"
    onError={onError}
  />
);

export default WordContentPicture;
