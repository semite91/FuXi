import './word_content_text.less';

interface WordContentTextProps {
  /** An older plain-text Content has no title. */
  title: string | null;
  content: string;
}

/** A story, quote or film reference. Both texts are React text nodes, so HTML in them is shown as text. */
const WordContentText = ({ title, content }: WordContentTextProps) => (
  <div className="word-content-text">
    {title !== null && <h3 className="word-content-text__title">{title}</h3>}
    <p className="word-content-text__content">{content}</p>
  </div>
);

export default WordContentText;
