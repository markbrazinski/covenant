import { useEffect, useState } from "react";

/**
 * Route-driven product state — a tiny History API router (no dependency added).
 *
 * Locked routes:
 *   /changes
 *   /changes/:changeId
 *   /changes/:changeId/impact
 *   /impact-plans
 *   /impact-plans/:planId
 */
export type RouteName = "changes" | "change" | "impact" | "plans" | "plan";
export interface Route {
  name: RouteName;
  changeId?: string;
  planId?: string;
}

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#/, "").split("/").filter(Boolean);
  if (parts[0] === "impact-plans" && parts[1]) {
    return { name: "plan", planId: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "impact-plans") return { name: "plans" };
  if (parts[0] === "changes" && parts[1] && parts[2] === "impact") {
    return { name: "impact", changeId: decodeURIComponent(parts[1]) };
  }
  if (parts[0] === "changes" && parts[1]) {
    return { name: "change", changeId: decodeURIComponent(parts[1]) };
  }
  return { name: "changes" };
}

export function useHashRoute(): [Route, (hash: string, replace?: boolean) => void] {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(typeof location !== "undefined" ? location.pathname : "")
  );
  useEffect(() => {
    const onRoute = () => setRoute(parseHash(location.pathname));
    if (location.pathname === "/") history.replaceState(null, "", "/changes");
    window.addEventListener("popstate", onRoute);
    onRoute();
    return () => window.removeEventListener("popstate", onRoute);
  }, []);
  const navigate = (hash: string, replace = false) => {
    const path = hash.replace(/^#/, "");
    if (location.pathname !== path) {
      if (replace) history.replaceState(null, "", path);
      else history.pushState(null, "", path);
    }
    setRoute(parseHash(path));
  };
  return [route, navigate];
}

/** Honor prefers-reduced-motion (and an optional forced override for dev). */
export function usePrefersReducedMotion(forced: boolean): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    if (typeof matchMedia === "undefined") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduce(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, []);
  return forced || reduce;
}
