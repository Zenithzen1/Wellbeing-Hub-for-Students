import { useCallback, useEffect, useRef, useState } from 'react';

/** Load data from the API: { data, error, loading, reload, setData }. `deps` re-run the loader. */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: undefined, error: null, loading: true });
  const seq = useRef(0);
  const run = useCallback(() => {
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    return Promise.resolve()
      .then(loader)
      .then((data) => { if (mine === seq.current) setState({ data, error: null, loading: false }); return data; })
      .catch((error) => { if (mine === seq.current) setState((s) => ({ ...s, error, loading: false })); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); }, [run]);
  const setData = useCallback((fn) => setState((s) => ({ ...s, data: typeof fn === 'function' ? fn(s.data) : fn })), []);
  return { ...state, reload: run, setData };
}

/** The time now, ticking every `every` ms (for countdowns and "in 20 minutes"). */
export function useNow(every = 15_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), every); return () => clearInterval(t); }, [every]);
  return now;
}
