// background.js
// Service worker for Chrome extension (can be expanded for notifications, etc.)

chrome.runtime.onInstalled.addListener(() => {
  console.log('Inpostly Instagram Scraper extension installed.');
});
