// The browser address. Kept apart so tests can replace it: jsdom cannot leave the page.

/** Loads another address in this tab. */
export const moveTo = (url: string): void => window.location.assign(url);
