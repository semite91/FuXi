import './navigation_menu.less';

export interface MenuItem {
  label: string;
  path: string;
}

interface NavigationMenuProps {
  items: readonly MenuItem[];
  onSelect: (path: string) => void;
}

/** A parchment sheet that unrolls from the menu button. The roll at its bottom edge travels down with it. */
const NavigationMenu = ({ items, onSelect }: NavigationMenuProps) => (
  <div className="navigation-menu" role="menu">
    <div className="navigation-menu__sheet">
      {items.map((item) => (
        <button
          key={item.path}
          type="button"
          className="navigation-menu__item"
          role="menuitem"
          onClick={() => onSelect(item.path)}
        >
          {item.label}
        </button>
      ))}
    </div>
    <div className="navigation-menu__roll" aria-hidden="true" />
  </div>
);

export default NavigationMenu;
