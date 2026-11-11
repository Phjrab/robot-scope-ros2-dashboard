// Observe the rendered predicate in the browser. A one-second Node poll can
// repeatedly miss the sub-second fresh window between two-second proposal reads.
// This does not refresh evidence, extend freshness, or send any command.
export async function waitForProposalReadiness(page) {
  const result = await page.waitForFunction(() => {
    const element = document.querySelector('[data-prep="details"]');
    if (!element?.textContent) return false;
    const details = JSON.parse(element.textContent);
    return details.proposal_cleanup?.state === 'SETTLED'
      && details.proposal_display_valid === true;
  }, null, { polling: 'raf', timeout: 5000 });
  await result.dispose();
}
