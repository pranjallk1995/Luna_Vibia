/** Talking to the gateway: JSON requests, their errors, and who is signed in. */

import { useQuery } from "@tanstack/react-query";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(body?.error ?? "The request failed. Please try again.", response.status);
  }
  return body as T;
}

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const remove = <T>(path: string) => request<T>(path, { method: "DELETE" });

export type Session<S> =
  | { status: "signed_out"; login_url: string }
  | { status: "forbidden"; email?: string; logout_url: string }
  | { status: "signed_in"; email?: string; logout_url: string; settings: S };

export function useSession<S>() {
  return useQuery({
    queryKey: ["session"],
    queryFn: () => request<Session<S>>("/auth/session"),
    staleTime: 60_000,
  });
}
