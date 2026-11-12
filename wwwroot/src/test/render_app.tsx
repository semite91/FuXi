// Renders the whole app at one address, with a router that tests can read.
import { render } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import App from '../app';

export const LOCATION_TEST_ID = 'location';

const LocationProbe = () => {
  const location = useLocation();

  return <span data-testid={LOCATION_TEST_ID}>{location.pathname + location.search}</span>;
};

export const renderApp = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  );
