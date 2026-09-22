"use client";
export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) { return <main className="login-page"><div className="login-card"><p className="eyebrow">OPERATION COULD NOT COMPLETE</p><h1>Something needs attention</h1><p>{error.message}</p><button className="button primary" onClick={reset}>Try again</button></div></main>; }
