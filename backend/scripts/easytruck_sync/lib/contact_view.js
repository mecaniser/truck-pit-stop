// DOM-only extraction, serialized unchanged into the source page by Playwright.
function readContactView() {
  // Verified AX contract: CUSTOMER h2, CONTACT details and exact account
  // navigation share a header ancestor; the contacts table is outside it.
  // A generic/global page header cannot establish this binding.
  let accountHeader = null;
  for (const heading of document.querySelectorAll('h2')) {
    for (let parent = heading.parentElement; parent && !parent.querySelector('table'); parent = parent.parentElement) {
      const links = [...parent.querySelectorAll('a[href]')].map(el => new URL(el.href).pathname);
      const labels = [...parent.querySelectorAll('*')].map(el => el.textContent.trim().toUpperCase());
      if (links.includes(location.pathname) && links.includes(location.pathname.replace(/\/contacts$/, ''))
          && labels.includes('CUSTOMER') && labels.includes('CONTACT')) {
        accountHeader = parent; break;
      }
    }
    if (accountHeader) break;
  }
  const searchFields = document.querySelectorAll('input#filter-search-input, #filter-search-input input, .filter-search-input input');
  const search = searchFields.length === 1 ? searchFields[0] : null;
  const archiveLabels = [...document.querySelectorAll('label')]
    .filter(el => el.textContent.trim() === 'Show archived');
  const archive = archiveLabels.length === 1 ? archiveLabels[0] : null;
  // ETS uses a text label and a separate sibling switch label, not a
  // native for/id association. Only accept the observed immediate wrapper.
  let checkbox = null;
  if (archive) {
    const wrapper = archive.parentElement;
    const controls = wrapper.querySelectorAll('input[type=checkbox]');
    const switches = wrapper.querySelectorAll(':scope > .inputContent > label.switch > input[type=checkbox]');
    const textLabels = [...wrapper.querySelectorAll('label')]
      .filter(el => el.textContent.trim() !== '');
    if (controls.length === 1 && switches.length === 1
        && controls[0] === switches[0] && textLabels.length === 1
        && textLabels[0] === archive) {
      checkbox = controls[0];
    }
  }
  const footer = [...document.querySelectorAll('p, div, span')].find(el => /^Showing\s+\d+\s+to\s+\d+\s+of\s+\d+\s+results$/.test(el.textContent.trim()));
  return {pathname: location.pathname, searchValue: search ? search.value : null,
    archived: checkbox ? checkbox.checked : null,
    headerBound: !!accountHeader,
    headerPhones: accountHeader ? [...accountHeader.querySelectorAll('a[href^="tel:"]')].map(el => el.textContent.trim()) : [],
    headers: [...document.querySelectorAll('table thead th, table thead td')].map(el => el.textContent.trim().toUpperCase()),
    rows: [...document.querySelectorAll('table tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim())),
    footer: footer ? footer.textContent.trim() : '',
    hasNext: [...document.querySelectorAll('a,button')].some(el => /^(Next|Next page|›|»)$/i.test(el.textContent.trim()) && !el.disabled && el.getAttribute('aria-disabled') !== 'true' && (el.tagName !== 'A' || el.hasAttribute('href')))};
}
module.exports = {readContactView};
