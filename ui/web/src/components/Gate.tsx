import { LogOut } from "lucide-react";

export const APP_NAME = "Luna Vibia";
export const SUBTITLE = "Private AI-managed music library";

export function Brand() {
  return (
    <div className="lv-header">
      <img className="lv-mark" src="/logo.png" alt={`${APP_NAME} logo`} />
      <div>
        <h1 className="lv-title">{APP_NAME}</h1>
        <p className="lv-subtitle">{SUBTITLE}</p>
      </div>
    </div>
  );
}

export function SignInPage({ url }: { url: string }) {
  return (
    <main className="lv-page lv-gate">
      <Brand />
      <a className="lv-google" href={url}>
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden="true">
          <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.92h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.41z" />
          <path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.62-2.43l-3.24-2.54c-.9.6-2.05.96-3.38.96-2.6 0-4.81-1.76-5.6-4.13H3.06v2.62A10 10 0 0 0 12 22z" />
          <path fill="#FBBC05" d="M6.4 13.86A6 6 0 0 1 6.08 12c0-.65.11-1.28.32-1.86V7.52H3.06A10 10 0 0 0 2 12c0 1.61.39 3.14 1.06 4.48l3.34-2.62z" />
          <path fill="#EA4335" d="M12 6.01c1.47 0 2.79.5 3.83 1.5l2.87-2.87A9.63 9.63 0 0 0 12 2a10 10 0 0 0-8.94 5.52l3.34 2.62C7.19 7.77 9.4 6.01 12 6.01z" />
        </svg>
        Continue with Google
      </a>
      <p className="lv-caption">One sign-in opens every Luna app.</p>
    </main>
  );
}

export function ForbiddenPage({ email, logoutUrl }: { email?: string; logoutUrl: string }) {
  return (
    <main className="lv-page lv-gate">
      <Brand />
      <p className="lv-alert lv-alert-error">
        {email ?? "This account"} is not authorized to access {APP_NAME}.
      </p>
      <a className="lv-button" href={logoutUrl}>
        <LogOut size={16} />
        Sign out
      </a>
    </main>
  );
}

export function UnreachablePage({ onRetry }: { onRetry: () => void }) {
  return (
    <main className="lv-page lv-gate">
      <Brand />
      <p className="lv-alert lv-alert-error">{APP_NAME} could not be reached.</p>
      <button className="lv-button" type="button" onClick={onRetry}>
        Try again
      </button>
    </main>
  );
}
