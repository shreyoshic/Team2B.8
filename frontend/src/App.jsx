
import "./App.css";
import { useEffect, useState } from "react";
import { apiRequest } from "./api";

function App() {
  const [page, setPage] = useState("welcome");
  const [user, setUser] = useState(null);
  const [files, setFiles] = useState([]);
  const [question, setQuestion] = useState("");
  const [url, setUrl] = useState("");
  const [links, setLinks] = useState([]);
  const [resolution, setResolution] = useState(null);
  const [questionResult, setQuestionResult] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      setFiles([]);
      return;
    }

    try {
      const saved = JSON.parse(
        localStorage.getItem(`uploadedFiles_${user.email}`) || "[]"
      );
      setFiles(Array.isArray(saved) ? saved : []);
    } catch {
      setFiles([]);
    }
  }, [user]);

  function saveFiles(updatedFiles) {
    setFiles(updatedFiles);

    if (user) {
      localStorage.setItem(
        `uploadedFiles_${user.email}`,
        JSON.stringify(updatedFiles)
      );
    }
  }

  async function handleFileChange(event) {
    const input = event.target;
    const selectedFiles = Array.from(input.files || []);

    if (!selectedFiles.length) return;

    setLoading(true);
    setError("");
    setMessage("");

    const uploaded = [];
    const failed = [];

    try {
      for (const selectedFile of selectedFiles) {
        try {
          const formData = new FormData();
          formData.append("file", selectedFile);

          const result = await apiRequest("/upload", {
            method: "POST",
            body: formData,
          });

          const filename =
            result.file || result.filename || selectedFile.name;

          uploaded.push({
            id: `${Date.now()}-${filename}`,
            filename,
            name: filename,
            size: selectedFile.size,
            recordsExtracted: result.records_extracted ?? 0,
            extractionStatus: result.extraction_status || "SUCCESS",
            ocrConfidence: result.ocr_confidence || [],
          });
        } catch (uploadError) {
          failed.push(
            `${selectedFile.name}: ${
              uploadError instanceof Error
                ? uploadError.message
                : "Upload failed"
            }`
          );
        }
      }

      if (uploaded.length > 0) {
        const existingNames = new Set(
          files.map((file) => file.filename || file.name)
        );

        const newFiles = uploaded.filter(
          (file) => !existingNames.has(file.filename)
        );

        saveFiles([...files, ...newFiles]);

        setMessage(
          uploaded
            .map(
              (file) =>
                `${file.filename}: ${file.recordsExtracted} records extracted`
            )
            .join("\n")
        );
      }

      if (failed.length > 0) {
        setError(failed.join("\n"));
      }
    } finally {
      setLoading(false);
      input.value = "";
    }
  }

  async function handleAddLink() {
    const submittedUrl = url.trim();

    if (!submittedUrl) {
      setError("Enter a URL first.");
      return;
    }

    let parsedUrl;

    try {
      parsedUrl = new URL(submittedUrl);
    } catch {
      setError("Enter a valid URL.");
      return;
    }

    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      setError("Only HTTP and HTTPS links are supported.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const result = await apiRequest("/ingest-url", {
        method: "POST",
        body: JSON.stringify({ url: submittedUrl }),
      });

      setLinks((previous) => [
        ...previous,
        {
          url: submittedUrl,
          name: result.title || result.filename || submittedUrl,
        },
      ]);

      setUrl("");
      setMessage(result.message || "Link processed successfully.");
    } catch (requestError) {
      setError(`Could not process link: ${requestError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleResolveConflict(conflict) {
    setLoading(true);
    setResolution(null);
    setError("");
    setMessage("");

    try {
      const result = await apiRequest("/resolve-conflict", {
        method: "POST",
        body: JSON.stringify({ conflict }),
      });

      setResolution(result);
      setMessage("Conflict analysis completed.");
    } catch (requestError) {
      setError(`Could not resolve conflict: ${requestError.message}`);
    } finally {
      setLoading(false);
    }
  }

  
async function removeFile(index) {
  const file = files[index];
  if (!file) return;

  const updatedFiles = files.filter((_, i) => i !== index);

  saveFiles(updatedFiles);
  setError("");
  setMessage(`${file.filename || file.name} removed from the document library.`);

  try {
    await apiRequest(
      `/documents/${encodeURIComponent(file.filename || file.name)}`,
      { method: "DELETE" }
    );
  } catch (requestError) {
    setMessage(
      `${file.filename || file.name} removed from the interface. Backend deletion failed: ${requestError.message}`
    );
  }
}


  
async function resetFiles() {
  const previousFiles = [...files];

  saveFiles([]);
  setQuestionResult(null);
  setResolution(null);
  setError("");
  setMessage("Document library cleared.");

  try {
    await apiRequest("/documents", { method: "DELETE" });
    setMessage("All documents deleted successfully.");
  } catch (requestError) {
    setMessage(
      `Document library cleared from the interface, but backend deletion failed: ${requestError.message}`
    );
  }
}


  async function handleAsk() {
    if (!question.trim()) {
      setError("Enter a question first.");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");
    setResolution(null);

    try {
      const result = await apiRequest("/question", {
        method: "POST",
        body: JSON.stringify({ question: question.trim() }),
      });

      setQuestionResult(result);
      setMessage(
        result.answer || result.message || "Question processed."
      );
    } catch (requestError) {
      setError(`Could not get an answer: ${requestError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateReport() {
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const report = await apiRequest("/report");

      const documents = Array.isArray(report.documents)
        ? report.documents
        : [];

      const temperatures = Array.isArray(report.temperatures_found)
        ? report.temperatures_found
        : [];

      const reportText = [
        "VERITRACE - CONSOLIDATED VERIFICATION REPORT",
        "=".repeat(48),
        "",
        `Status: ${report.report_status || "NOT SPECIFIED"}`,
        `Documents processed: ${report.documents_count ?? documents.length}`,
        `Message: ${report.message || "No additional message."}`,
        "",
        "DOCUMENTS",
        ...documents.map(
          (doc) =>
            `${doc.filename || "Unknown document"} | Pages: ${doc.pages ?? "N/A"}`
        ),
        "",
        "DETECTED TEMPERATURES",
        ...temperatures.map(
          (item) =>
            `${item.temperature_celsius ?? "N/A"}°C | ${
              item.document || "Unknown document"
            } | Page ${item.page ?? "N/A"}`
        ),
        "",
        "REVIEW NOTE",
        "Review extracted values and their source citations. Treat differences as potential conflicts until their context is verified.",
        "",
        "Generated by VeriTrace",
      ].join("\n");

      const blob = new Blob([reportText], {
        type: "text/plain;charset=utf-8",
      });

      const downloadUrl = URL.createObjectURL(blob);
      const downloadLink = document.createElement("a");

      downloadLink.href = downloadUrl;
      downloadLink.download = "VeriTrace_Report.txt";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      downloadLink.remove();
      URL.revokeObjectURL(downloadUrl);

      setMessage("Report generated and downloaded successfully.");
    } catch (requestError) {
      setError(`Could not generate report: ${requestError.message}`);
    } finally {
      setLoading(false);
    }
  }

  function handleRegister(event) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") || "").trim();
    const email = String(form.get("email") || "").trim().toLowerCase();
    const password = String(form.get("password") || "");

    if (!name || !email || password.length < 8) {
      setError("Enter all details. Password must be at least 8 characters.");
      return;
    }

    setError("");
    setMessage(
      "Registration is not connected to backend authentication yet. No account was created."
    );
  }

  function handleLogin(event) {
    event.preventDefault();

    setError("");
    setMessage(
      "Login is not connected to backend authentication yet. No account was authenticated."
    );
  }

  function logout() {
    setUser(null);
    setFiles([]);
    setLinks([]);
    setQuestion("");
    setUrl("");
    setQuestionResult(null);
    setResolution(null);
    setMessage("");
    setError("");
    setPage("welcome");
  }

  function startDemo() {
    setUser({
      name: "Demo User",
      email: "demo@veritrace.local",
      role: "user",
      demo: true,
    });

    setPage("dashboard");
    setMessage(
      "Demo workspace opened. Authentication and private document storage are not enabled."
    );
    setError("");
  }

  if (page === "welcome") {
    return (
      <div className="auth-page">
        <div className="auth-layout">
          <div className="auth-intro">
            <div className="brand-mark">
              <span className="brand-symbol">V</span>
              VeriTrace
            </div>

            <h1>
              Evidence you can <span>trace.</span>
            </h1>

            <p>
              Bring documents together, examine evidence, identify
              inconsistencies, and build reports where every claim can
              be traced to its source.
            </p>

            <div className="auth-features">
              <div className="auth-feature">
                <span>✓</span> Multi-source document analysis
              </div>
              <div className="auth-feature">
                <span>✓</span> Traceable evidence and citations
              </div>
              <div className="auth-feature">
                <span>✓</span> Conflict-aware verification
              </div>
            </div>
          </div>

          <div className="auth-card">
            <h2>Get started</h2>
            <p className="auth-subtitle">
              Your workspace for evidence-grounded documents.
            </p>

            <button
              className="auth-primary-button"
              onClick={() => {
                setMessage("");
                setError("");
                setPage("register");
              }}
            >
              Create an account
            </button>

            <button
              className="auth-primary-button"
              style={{
                marginTop: 12,
                background: "transparent",
                color: "#38bdf8",
              }}
              onClick={() => {
                setMessage("");
                setError("");
                setPage("login");
              }}
            >
              Log in
            </button>

            <p className="auth-switch">Want to explore the interface?</p>

            <button
              className="auth-primary-button"
              onClick={startDemo}
            >
              Open demo workspace
            </button>

            <p className="auth-footer">
              Demo mode is for interface testing only. It does not
              provide authenticated or private storage.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (page === "register") {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ width: "min(100%, 460px)" }}>
          <button
            className="auth-back"
            onClick={() => {
              setError("");
              setMessage("");
              setPage("welcome");
            }}
          >
            ← Back
          </button>

          <h2>Create your account</h2>
          <p className="auth-subtitle">
            Set up your VeriTrace workspace.
          </p>

          <form className="auth-form" onSubmit={handleRegister}>
            <div className="auth-field">
              <label htmlFor="register-name">Full name</label>
              <input id="register-name" name="name" required />
            </div>

            <div className="auth-field">
              <label htmlFor="register-email">Email address</label>
              <input
                id="register-email"
                name="email"
                type="email"
                required
              />
            </div>

            <div className="auth-field">
              <label htmlFor="register-password">Password</label>
              <input
                id="register-password"
                name="password"
                type="password"
                minLength={8}
                required
              />
            </div>

            <div className="auth-field">
              <label htmlFor="register-role">Workspace role</label>
              <select id="register-role" name="role">
                <option value="user">Standard user</option>
                <option value="analyst">Analyst</option>
                <option value="reviewer">Reviewer</option>
              </select>
            </div>

            <button className="auth-primary-button" type="submit">
              Create account
            </button>
          </form>

          {error && (
            <p className="auth-message" role="alert">{error}</p>
          )}
          {message && (
            <p className="auth-message" role="status">{message}</p>
          )}

          <p className="auth-switch">
            Already registered?{" "}
            <button
              className="auth-link"
              onClick={() => {
                setMessage("");
                setError("");
                setPage("login");
              }}
            >
              Log in
            </button>
          </p>
        </div>
      </div>
    );
  }

  if (page === "login") {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ width: "min(100%, 460px)" }}>
          <button
            className="auth-back"
            onClick={() => {
              setError("");
              setMessage("");
              setPage("welcome");
            }}
          >
            ← Back
          </button>

          <h2>Welcome back</h2>
          <p className="auth-subtitle">
            Log in to access your document workspace.
          </p>

          <form className="auth-form" onSubmit={handleLogin}>
            <div className="auth-field">
              <label htmlFor="login-email">Email address</label>
              <input
                id="login-email"
                name="email"
                type="email"
                required
              />
            </div>

            <div className="auth-field">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                name="password"
                type="password"
                required
              />
            </div>

            <button className="auth-primary-button" type="submit">
              Log in
            </button>
          </form>

          {error && (
            <p className="auth-message" role="alert">{error}</p>
          )}
          {message && (
            <p className="auth-message" role="status">{message}</p>
          )}

          <p className="auth-switch">
            New to VeriTrace?{" "}
            <button
              className="auth-link"
              onClick={() => {
                setMessage("");
                setError("");
                setPage("register");
              }}
            >
              Create an account
            </button>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>VeriTrace</h1>
          <p>Multi-Source Ingestion into a Single Verifiable Document</p>
        </div>

        <div style={{ marginTop: 18 }}>
          <span style={{ color: "#94a3b8", marginRight: 14 }}>
            {user?.name}
          </span>
          <button className="reset-button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>

      <main className="container">
        <section className="section">
          <h2>Document workspace</h2>
          <p style={{ color: "#94a3b8" }}>
            Upload source documents and work with their evidence.
          </p>

          <label className="upload-box">
            <input
              type="file"
              multiple
              accept=".pdf,.txt,.log,.docx,.pptx,.xlsx,.csv,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              disabled={loading}
            />
            <span className="upload-icon">+</span>
            <strong>Choose documents</strong>
            <span>
              PDF, TXT, LOG, DOCX, PPTX, XLSX, CSV and images
            </span>
          </label>

          <div className="question-box" style={{ marginTop: 16 }}>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleAddLink();
              }}
              placeholder="Paste a public webpage or document URL..."
            />

            <button
              className="ask-button"
              onClick={handleAddLink}
              disabled={loading}
            >
              {loading ? "Processing..." : "Add Link"}
            </button>
          </div>

          {links.length > 0 && (
            <div className="file-list-container">
              <h3>Internet Sources</h3>

              <div className="file-list">
                {links.map((link, index) => (
                  <div
                    className="file-item"
                    key={`${link.url}-${index}`}
                  >
                    <div className="file-info">
                      <span className="file-icon">URL</span>
                      <div>
                        <strong>{link.name}</strong>
                        <a
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: "block",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {link.url}
                        </a>
                      </div>
                    </div>

                    <button
                      className="remove-button"
                      onClick={() =>
                        setLinks((previous) =>
                          previous.filter((_, i) => i !== index)
                        )
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {files.length > 0 && (
            <div className="file-list-container">
              <div className="file-list-header">
                <h3>Document library</h3>
                <button
                  className="reset-button"
                  onClick={resetFiles}
                  disabled={loading}
                >
                  Clear list
                </button>
              </div>

              <div className="file-list">
                {files.map((file, index) => (
                  <div
                    className="file-item"
                    key={file.id || `${file.name}-${index}`}
                  >
                    <div className="file-info">
                      <span className="file-icon">
                        {(file.name?.split(".").pop() || "FILE")
                          .slice(0, 4)
                          .toUpperCase()}
                      </span>

                      <div>
                        <strong>{file.name || file.filename}</strong>
                        <span>
                          {((file.size || 0) / 1024).toFixed(1)} KB
                        </span>
                        <span>
                          {file.recordsExtracted ?? 0} records extracted
                        </span>
                        <span>
                          Status: {file.extractionStatus || "SUCCESS"}
                        </span>
                      </div>
                    </div>

                    <button
                      className="remove-button"
                      onClick={() => removeFile(index)}
                      disabled={loading}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="section">
          <div className="section-title">
            <div>
              <h2>Ask a question</h2>
              <p>Ask about evidence in your source documents.</p>
            </div>
          </div>

          <div className="question-box">
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !loading) handleAsk();
              }}
              placeholder="Ask a question about your evidence..."
            />

            <button
              className="ask-button"
              onClick={handleAsk}
              disabled={loading}
            >
              {loading ? "Asking..." : "Ask"}
            </button>
          </div>

          {error && (
            <p
              className="auth-message"
              role="alert"
              style={{ color: "#fca5a5", whiteSpace: "pre-wrap" }}
            >
              {error}
            </p>
          )}

          {message && (
            <p
              className="auth-message"
              role="status"
              style={{ whiteSpace: "pre-wrap" }}
            >
              {message}
            </p>
          )}

          {questionResult && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr)",
                gap: 16,
                marginTop: 22,
              }}
            >
              <div
                style={{
                  background: "rgba(15, 23, 42, 0.72)",
                  border: "1px solid rgba(96, 165, 250, 0.35)",
                  borderRadius: 14,
                  padding: 20,
                  minWidth: 0,
                }}
              >
                <h3 style={{ marginTop: 0, color: "#93c5fd" }}>
                  Answer
                </h3>
                <p
                  style={{
                    color: "#e2e8f0",
                    lineHeight: 1.7,
                    overflowWrap: "anywhere",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {questionResult.answer || "No answer returned."}
                </p>
              </div>

              <div
                style={{
                  background: "rgba(15, 23, 42, 0.72)",
                  border: "1px solid rgba(167, 139, 250, 0.35)",
                  borderRadius: 14,
                  padding: 20,
                  minWidth: 0,
                }}
              >
                <h3 style={{ marginTop: 0, color: "#c4b5fd" }}>
                  Sources
                </h3>

                {questionResult.sources?.length > 0 ? (
                  <ul
                    style={{
                      color: "#e2e8f0",
                      lineHeight: 1.8,
                      paddingLeft: 20,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {questionResult.sources.map((source, index) => (
                      <li key={index}>
                        {typeof source === "string"
                          ? source
                          : JSON.stringify(source)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ color: "#94a3b8" }}>
                    No sources returned.
                  </p>
                )}
              </div>

              <div
                style={{
                  background: "rgba(15, 23, 42, 0.72)",
                  border: "1px solid rgba(52, 211, 153, 0.35)",
                  borderRadius: 14,
                  padding: 20,
                  minWidth: 0,
                }}
              >
                <h3 style={{ marginTop: 0, color: "#6ee7b7" }}>
                  Verification status
                </h3>
                <p
                  style={{
                    display: "inline-block",
                    padding: "7px 11px",
                    borderRadius: 999,
                    background: "rgba(52, 211, 153, 0.12)",
                    color: "#a7f3d0",
                    fontWeight: 600,
                    overflowWrap: "anywhere",
                  }}
                >
                  {questionResult.verification_status || "PENDING"}
                </p>
              </div>

              <div
                style={{
                  background: "rgba(15, 23, 42, 0.72)",
                  border: "1px solid rgba(248, 113, 113, 0.35)",
                  borderRadius: 14,
                  padding: 20,
                  minWidth: 0,
                }}
              >
                <h3 style={{ marginTop: 0, color: "#fca5a5" }}>
                  Potential conflicts
                </h3>

                {questionResult.conflicts?.length > 0 ? (
                  <ul
                    style={{
                      color: "#e2e8f0",
                      lineHeight: 1.8,
                      paddingLeft: 20,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {questionResult.conflicts.map((conflict, index) => (
                      <li key={index} style={{ marginBottom: 12 }}>
                        <div>
                          {conflict.document || "Unknown document"}
                          {conflict.temperature_celsius != null
                            ? `: ${conflict.temperature_celsius}°C`
                            : ""}
                          {conflict.page != null
                            ? `, page ${conflict.page}`
                            : ""}
                        </div>

                        <button
                          className="ask-button"
                          style={{ marginTop: 8 }}
                          disabled={loading}
                          onClick={() => handleResolveConflict(conflict)}
                        >
                          Resolve Conflict
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ color: "#94a3b8" }}>
                    No potential conflicts returned for this question.
                  </p>
                )}
              </div>

              {resolution && (
                <div
                  className="file-list-container"
                  style={{ marginTop: 4 }}
                >
                  <h3>Conflict Resolution</h3>

                  <p>
                    <strong>Status:</strong>{" "}
                    {resolution.status || "REVIEW_REQUIRED"}
                  </p>

                  <p>
                    <strong>Recommendation:</strong>{" "}
                    {resolution.recommendation ||
                      "No recommendation returned."}
                  </p>

                  <p>
                    <strong>Explanation:</strong>{" "}
                    {resolution.reasoning ||
                      resolution.explanation ||
                      "No explanation returned."}
                  </p>

                  <h4>Supporting Evidence</h4>

                  {resolution.sources?.length > 0 ? (
                    <ul>
                      {resolution.sources.map((source, index) => (
                        <li key={index}>
                          {typeof source === "string"
                            ? source
                            : `${source.name || source.document || "Source"}: ${
                                source.claim || source.text || ""
                              }`}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>No supporting sources were returned.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </section>

        <section className="section">
          <h2>Reports and history</h2>
          <p style={{ color: "#94a3b8" }}>
            Generate a consolidated report containing uploaded documents,
            detected temperatures, and the current verification status.
          </p>

          <button
            className="ask-button"
            onClick={handleGenerateReport}
            disabled={loading}
          >
            {loading ? "Generating Report..." : "Generate & Download Report"}
          </button>
        </section>
      </main>
    </div>
  );
}

export default App;
