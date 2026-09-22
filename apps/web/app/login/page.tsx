export default async function Login({ searchParams }: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return <main className="login-page">
    <form action="/api/login" method="post" className="login-card">
      <p className="eyebrow">THAAZHAI OPERATIONS</p>
      <h1>Team access</h1>
      <p>Enter the access code shared by your administrator. Your code gives you either view-only or administrator access.</p>
      <label>Access code<input name="token" type="password" required autoFocus /></label>
      {error && <div className="alert error">That token is not valid.</div>}
      <button className="button primary">Sign in</button>
    </form>
  </main>;
}
