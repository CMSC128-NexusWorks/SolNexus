const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function App() {
  return (
    <main>
      <h1>SolNexus</h1>
      <p>Lead and client communication pipeline for SolTech EMR.</p>
      <p>
        API base URL: <code>{apiUrl}</code>
      </p>
    </main>
  );
}

export default App;
