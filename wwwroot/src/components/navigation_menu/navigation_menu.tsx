import './navigation_menu.less';

export interface MenuItem {
  label: string;
  path: string;
}

interface NavigationMenuProps {
  items: readonly MenuItem[];
  onSelect: (path: string) => void;
}

const NavigationMenu = ({ items, onSelect }: NavigationMenuProps) => (
  <div className="navigation-menu" role="menu">
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
);

export default NavigationMenu;
