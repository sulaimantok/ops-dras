// Disable submit buttons on submit, site-wide, so a double-click (or an
// impatient second click while a full-page POST is in flight) can't fire
// the same backup/restore/save request twice. If the browser blocks
// navigation (e.g. validation failure) the buttons re-enable automatically
// since the page never actually unloads.
document.addEventListener("submit", (event) => {
  event.target.querySelectorAll('button[type="submit"]').forEach((btn) => {
    btn.disabled = true;
  });
});
