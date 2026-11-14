import './credits.less';

interface CreditsProps {
  title: string;
  logoSource: string;
  logoText: string;
  noticeText: string;
}

/** The notice a data source asks for: its logo and its sentence. */
const Credits = ({ title, logoSource, logoText, noticeText }: CreditsProps) => (
  <footer className="credits">
    <h2 className="credits__title">{title}</h2>
    <img className="credits__logo" src={logoSource} alt={logoText} />
    <p className="credits__notice">{noticeText}</p>
  </footer>
);

export default Credits;
