/** The PIN in front of the Hidden tab; this file is identical in Luna Visia, Lexia, and Vibia. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, LockOpen } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

type PinStatus = { pin_set: boolean; unlocked: boolean; locked_seconds: number; settings_url: string };

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = await response.json().catch(() => null);
  if (!response.ok) throw new Error(answer?.error ?? "The request failed. Please try again.");
  return answer as T;
}

const lockNow = () => fetch("/app/hidden/lock", { method: "POST", keepalive: true }).catch(() => undefined);

/** Show ``children`` only once the person's PIN has unlocked hidden items; leaving locks them again. */
export function HiddenGate({ noun, children }: { noun: string; children: ReactNode }) {
  const client = useQueryClient();
  const [pin, setPin] = useState("");
  const status = useQuery({
    queryKey: ["hidden-pin"],
    queryFn: () => call<PinStatus>("/app/hidden/pin"),
    // Hidden items lock again after a while idle; this notices without a reload.
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const unlock = useMutation({
    mutationFn: (typed: string) => call<{ unlocked: boolean }>("/app/hidden/unlock", { pin: typed }),
    onSettled: () => setPin(""),
    onSuccess: () => client.invalidateQueries(),
  });
  const lock = useMutation({
    mutationFn: lockNow,
    onSuccess: () => client.invalidateQueries({ queryKey: ["hidden-pin"] }),
  });

  // Switching to another tab, or closing the page, locks hidden items.
  useEffect(() => () => void lockNow(), []);

  if (status.isPending) return <p className="lv-caption">Checking whether hidden {noun} are unlocked…</p>;
  if (status.isError) return <p className="lv-alert lv-alert-error">{status.error.message}</p>;
  const { pin_set, unlocked, locked_seconds, settings_url } = status.data;

  if (unlocked) {
    return (
      <>
        <div className="lv-pin-bar">
          <span>
            <LockOpen size={15} /> Hidden {noun} are unlocked until you leave this tab or stay idle for 10 minutes.
          </span>
          <button className="lv-button" type="button" onClick={() => lock.mutate()}>
            <Lock size={15} />
            Lock
          </button>
        </div>
        {children}
      </>
    );
  }

  if (!pin_set) {
    return (
      <section className="lv-pin">
        <Lock size={28} />
        <h2>Hidden {noun} need a PIN</h2>
        <p className="lv-caption">
          Set one PIN in Luna Sentia and it guards the hidden items in Luna Visia, Lexia, and Vibia.
        </p>
        <a className="lv-button lv-button-primary" href={settings_url}>
          Set your PIN
        </a>
      </section>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pin) unlock.mutate(pin);
  };
  const minutes = Math.ceil(locked_seconds / 60);
  return (
    <form className="lv-pin" onSubmit={submit}>
      <Lock size={28} />
      <h2>Enter your PIN to see hidden {noun}</h2>
      <input
        className="lv-input lv-pin-input"
        type="password"
        inputMode="numeric"
        autoComplete="off"
        maxLength={12}
        aria-label="PIN"
        value={pin}
        onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
        disabled={locked_seconds > 0 || unlock.isPending}
        autoFocus
      />
      <button className="lv-button lv-button-primary" type="submit" disabled={!pin || locked_seconds > 0 || unlock.isPending}>
        {unlock.isPending ? "Checking…" : "Unlock"}
      </button>
      {locked_seconds > 0 && !unlock.isError && (
        <p className="lv-alert lv-alert-error">Too many wrong PINs. Try again in {minutes} minutes.</p>
      )}
      {unlock.isError && <p className="lv-alert lv-alert-error">{unlock.error.message}</p>}
      <a className="lv-caption" href={settings_url}>
        Forgot your PIN? Set a new one in Luna Sentia.
      </a>
    </form>
  );
}
