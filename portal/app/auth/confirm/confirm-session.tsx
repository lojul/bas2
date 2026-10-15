"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/browser";

function loginWithError(reason: string, next: string) {
  const url = new URL("/login", window.location.origin);
  url.searchParams.set("error", "link");
  url.searchParams.set("reason", reason.replace(/[^\w.-]/g, "").slice(0, 60));
  url.searchParams.set("next", next);
  window.location.replace(url);
}

export function ConfirmSession({ next }: { next: string }) {
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const hash = new URLSearchParams(window.location.hash.slice(1));
    // Remove the tokens from the address bar and browser history straight away.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);

    const accessToken = hash.get("access_token");
    const refreshToken = hash.get("refresh_token");
    if (accessToken && refreshToken) {
      // setSession checks the token with Supabase, then writes the session cookies in this
      // browser; the server and proxy.ts read the same cookies on the next request.
      createClient()
        .auth.setSession({ access_token: accessToken, refresh_token: refreshToken })
        .then(({ error }) => {
          if (error) loginWithError(error.code ?? error.name, next);
          else window.location.replace(next);
        })
        .catch(() => loginWithError("invalid_token", next));
      return;
    }

    // A link from the PKCE flow still goes through the server callback.
    const query = new URLSearchParams(window.location.search);
    if (query.get("code") || query.get("token_hash")) {
      window.location.replace(`/auth/callback${window.location.search}`);
      return;
    }

    loginWithError(hash.get("error_code") ?? query.get("error_code") ?? "missing_tokens", next);
  }, [next]);

  return <p className="text-sm text-genie-muted">Signing you in…</p>;
}
