/** Cancel obsolete requests and reject late completions, even if transport ignores abort. */
export function createLatestRequest() {
  let active: AbortController | null = null;
  const cancel = () => {
    active?.abort();
    active = null;
  };
  return {
    cancel,
    start() {
      cancel();
      const controller = new AbortController();
      active = controller;
      return {
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]),
        isCurrent: () => active === controller && !controller.signal.aborted,
      };
    },
  };
}
