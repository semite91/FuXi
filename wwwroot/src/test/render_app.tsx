// Renders the whole app at one address, with a router that tests can read.
import { render } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router';
import App from '../app';

export const LOCATION_TEST_ID = 'location';

const LocationProbe = () => {
  const location = useLocation();

  return <span data-testid={LOCATION_TEST_ID}>{location.pathname + location.search}</span>;
};

export const NAVIGATE_TEST_ID = 'navigate-probe';

/** A click navigates to its data-to address, the way a notification click opens a route. */
const NavigateProbe = () => {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      hidden
      data-testid={NAVIGATE_TEST_ID}
      onClick={(event) => void navigate(event.currentTarget.dataset.to ?? '/')}
    />
  );
};

export const renderApp = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
      <NavigateProbe />
    </MemoryRouter>,
  );
