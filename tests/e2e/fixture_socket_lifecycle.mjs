// Socket close is not guaranteed during page/context teardown.
export function onFixtureSocketClose(page, socket, cleanup) {
  let closed = false;
  const dispose = () => {
    if (closed) return;
    closed = true;
    page.off('close', dispose);
    cleanup();
  };
  page.once('close', dispose);
  socket.onClose(dispose);
}
