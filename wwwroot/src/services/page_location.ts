// The browser address and windows. Kept apart so tests can replace it: jsdom cannot leave the page.

/** Loads another address in this tab. */
export const moveTo = (url: string): void => window.location.assign(url);

/** Opens an address in a new tab and leaves this one where it is. */
export const openInNewTab = (url: string): void => {
  window.open(url, '_blank');
};

/** Closes this tab. The browser allows it only for a tab the app opened itself; otherwise nothing happens. */
export const closeThisTab = (): void => window.close();
