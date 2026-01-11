export default function NotFound() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 560 }}>
        <div style={{ fontSize: 12, opacity: 0.7, letterSpacing: 0.6 }}>
          404
        </div>
        <h1 style={{ margin: "8px 0 8px", fontSize: 28 }}>Page not found</h1>
        <p style={{ margin: 0, opacity: 0.75 }}>
          This route doesn’t exist. Go back to the chat and continue from there.
        </p>
      </div>
    </main>
  );
}
