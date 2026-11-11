import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";

export type BackendState = "connected" | "disconnected" | "reconnecting";

const RETRY_DELAYS_MS = [2000, 5000, 10000, 30000];
const HEARTBEAT_MS = 30000;

/**
 * 后端连通性：启动探活、断线退避重连、30 秒心跳（2026-11-11 从 AppShell 拆出）。
 *
 * 心跳成功时不写状态（已经是 connected 就不触发渲染）；拆分前后行为一致，
 * `AppShell.render.test.tsx` 钉住这一点。
 */
export function useBackendHealth(onReconnected?: () => Promise<unknown> | void) {
  const [state, setState] = useState<BackendState>("connected");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const check = async (tries = 0) => {
      try {
        await api.health();
        if (!cancelled) {
          setState("connected");
          setAttempt(0);
        }
      } catch {
        if (cancelled) return;
        setState("disconnected");
        setAttempt(tries + 1);
        timer = window.setTimeout(() => {
          setState("reconnecting");
          void check(tries + 1);
        }, RETRY_DELAYS_MS[Math.min(tries, RETRY_DELAYS_MS.length - 1)]);
      }
    };
    void check();
    const interval = window.setInterval(() => void api.health().catch(() => void check()), HEARTBEAT_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const reconnect = useCallback(async () => {
    setState("reconnecting");
    try {
      await api.health();
      setState("connected");
      setAttempt(0);
      await onReconnected?.();
    } catch {
      setState("disconnected");
    }
  }, [onReconnected]);

  return { state, attempt, reconnect };
}
