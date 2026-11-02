// Socket close is not guaranteed during page/context teardown.
export function onFixtureSocketClose(page, socket, cleanup) {
  const context = page.context();
  let closed = false;
  const dispose = () => {
    if (closed) return;
    closed = true;
    page.off('close', dispose);
    context.off('close', dispose);
    cleanup();
  };
  page.once('close', dispose);
  context.once('close', dispose);
  socket.onClose(dispose);
  return dispose;
}
