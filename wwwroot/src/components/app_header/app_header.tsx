import { useEffect, useRef, useState } from 'react';
import IconButton from '../icon_button/icon_button';
import NavigationMenu, { type MenuItem } from '../navigation_menu/navigation_menu';
import './app_header.less';

const ESCAPE_KEY = 'Escape';
const KEY_DOWN_EVENT = 'keydown';
const POINTER_DOWN_EVENT = 'mousedown';

interface AppHeaderProps {
  logoSource: string;
  logoText: string;
  menuLabel: string;
  items: readonly MenuItem[];
  onNavigate: (path: string) => void;
}

/** The logo and the menu button. The menu closes on a choice, on Escape and on a click outside it. */
const AppHeader = ({ logoSource, logoText, menuLabel, items, onNavigate }: AppHeaderProps) => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) {
      return undefined;
    }

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === ESCAPE_KEY) {
        setIsMenuOpen(false);
      }
    };
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (event.target instanceof Node && !menuAreaRef.current?.contains(event.target)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener(KEY_DOWN_EVENT, closeOnEscape);
    document.addEventListener(POINTER_DOWN_EVENT, closeOnOutsideClick);

    return () => {
      document.removeEventListener(KEY_DOWN_EVENT, closeOnEscape);
      document.removeEventListener(POINTER_DOWN_EVENT, closeOnOutsideClick);
    };
  }, [isMenuOpen]);

  const select = (path: string) => {
    setIsMenuOpen(false);
    onNavigate(path);
  };

  return (
    <header className="app-header">
      <img className="app-header__logo" src={logoSource} alt={logoText} />
      <div className="app-header__menu" ref={menuAreaRef}>
        <IconButton
          icon="menu"
          shape="square"
          label={menuLabel}
          aria-haspopup="true"
          aria-expanded={isMenuOpen}
          onClick={() => setIsMenuOpen((isOpen) => !isOpen)}
        />
        {isMenuOpen && <NavigationMenu items={items} onSelect={select} />}
      </div>
    </header>
  );
};

export default AppHeader;
