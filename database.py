"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Code2, Bug, Zap, RefreshCw, TestTube, MessageSquare,
  Copy, Check, Loader2, ChevronDown, FileCode, Play,
  FolderInput, Wand2, ArrowLeft, Sparkles,
} from "lucide-react";

const LANGUAGES = [
  "Python", "JavaScript", "TypeScript", "React", "Node.js",
  "Go", "Rust", "Java", "C++", "C#", "PHP", "Swift",
  "Kotlin", "SQL", "Bash", "HTML/CSS",
];

const ACTIONS = [
  { id: "explain", label: "Explain", icon: <MessageSquare size={14} />, color: "#3B82F6", description: "Break down what this code does" },
  { id: "debug", label: "Debug", icon: <Bug size={14} />, color: "#EF4444", description: "Find and fix bugs" },
  { id: "optimize", label: "Optimize", icon: <Zap size={14} />, color: "#D4AF37", description: "Make it faster & cleaner" },
  { id: "convert", label: "Convert", icon: <RefreshCw size={14} />, color: "#A855F7", description: "Rewrite in another language" },
  { id: "test", label: "Write Tests", icon: <TestTube size={14} />, color: "#22C55E", description: "Generate unit tests" },
  { id: "comment", label: "Add Comments", icon: <Code2 size={14} />, color: "#F97316", description: "Document the code" },
];

// ---------------------------------------------------------------------------
// Language auto-detection
// ---------------------------------------------------------------------------
// Each language has a set of weighted signature patterns. We score every
// language against the pasted code and pick the highest-scoring match above
// a minimum confidence threshold. This is intentionally heuristic (no real
// parser) but is accurate enough for the common cases people paste.

type LangRule = { name: string; patterns: RegExp[]; weight?: number };

const LANG_RULES: LangRule[] = [
  {
    name: "Python",
    patterns: [
      /^\s*def\s+\w+\s*\(.*\):/m,
      /^\s*import\s+\w+/m,
      /^\s*from\s+\w+\s+import\s+/m,
      /elif\s+.*:/,
      /:\s*$/m,
      /self\./,
      /print\(/,
      /^\s*#.*$/m,
      /f"[^"]*\{/,
      /^\s*class\s+\w+.*:\s*$/m,
    ],
  },
  {
    name: "TypeScript",
    patterns: [
      /:\s*(string|number|boolean|void|any|unknown)\b/,
      /interface\s+\w+\s*\{/,
      /type\s+\w+\s*=/,
      /<\w+>\(/,
      /:\s*React\.\w+/,
      /as\s+const/,
    ],
    weight: 1.1,
  },
  {
    name: "React",
    patterns: [
      /import\s+.*from\s+["']react["']/,
      /useState\(/,
      /useEffect\(/,
      /<\/?[A-Z]\w*[\s/>]/,
      /className=/,
      /export default function/,
    ],
    weight: 1.1,
  },
  {
    name: "Node.js",
    patterns: [
      /require\(["']/,
      /module\.exports/,
      /process\.env/,
      /app\.(get|post|put|delete)\(/,
    ],
  },
  {
    name: "JavaScript",
    patterns: [
      /\bfunction\s+\w+\s*\(/,
      /=>\s*\{?/,
      /\bconst\s+\w+\s*=/,
      /\blet\s+\w+\s*=/,
      /console\.log\(/,
      /document\./,
    ],
  },
  {
    name: "Go",
    patterns: [
      /^package\s+main/m,
      /func\s+main\s*\(\s*\)/,
      /fmt\.(Println|Printf|Print)\(/,
      /:=\s*/,
      /^import\s*\(/m,
    ],
  },
  {
    name: "Rust",
    patterns: [
      /fn\s+main\s*\(\s*\)/,
      /println!\(/,
      /let\s+mut\s+/,
      /use\s+std::/,
      /->\s*\w+\s*\{/,
    ],
  },
  {
    name: "Java",
    patterns: [
      /public\s+class\s+\w+/,
      /public\s+static\s+void\s+main\s*\(/,
      /System\.out\.println\(/,
      /^\s*import\s+java\./m,
    ],
  },
  {
    name: "C++",
    patterns: [
      /#include\s*<iostream>/,
      /std::/,
      /cout\s*<</,
      /int\s+main\s*\(\s*\)/,
      /#include\s*<\w+(\.h)?>/,
    ],
  },
  {
    name: "C#",
    patterns: [
      /using\s+System;/,
      /namespace\s+\w+/,
      /Console\.WriteLine\(/,
      /public\s+class\s+\w+/,
    ],
  },
  {
    name: "PHP",
    patterns: [
      /<\?php/,
      /\$\w+\s*=/,
      /echo\s+/,
      /function\s+\w+\s*\(.*\)\s*\{/,
    ],
  },
  {
    name: "Swift",
    patterns: [
      /^\s*func\s+\w+\s*\(/m,
      /\bvar\s+\w+\s*:/,
      /\blet\s+\w+\s*:/,
      /import\s+(Swift|UIKit|SwiftUI)/,
    ],
  },
  {
    name: "Kotlin",
    patterns: [
      /fun\s+main\s*\(/,
      /\bval\s+\w+\s*=/,
      /\bvar\s+\w+\s*:/,
      /println\(/,
    ],
  },
  {
    name: "SQL",
    patterns: [
      /\bSELECT\b[\s\S]*\bFROM\b/i,
      /\bINSERT\s+INTO\b/i,
      /\bCREATE\s+TABLE\b/i,
      /\bWHERE\b/i,
      /\bJOIN\b/i,
    ],
    weight: 1.2,
  },
  {
    name: "Bash",
    patterns: [
      /^#!\/bin\/(bash|sh)/,
      /^\s*if\s*\[\[/m,
      /\$\{?\w+\}?/,
      /^\s*echo\s+/m,
    ],
  },
  {
    name: "HTML/CSS",
    patterns: [
      /<!DOCTYPE html>/i,
      /<html[\s>]/i,
      /<div[\s>]/i,
      /^\s*[.#]?[\w-]+\s*\{[^}]*\}/m,
    ],
  },
];

function detectLanguage(code: string): string | null {
  const trimmed = code.trim();
  if (trimmed.length < 12) return null; // not enough signal yet

  let best: { name: string; score: number } | null = null;

  for (const rule of LANG_RULES) {
    let score = 0;
    for (const pattern of rule.patterns) {
      if (pattern.test(trimmed)) score += 1;
    }
    score *= rule.weight ?? 1;
    if (score > 0 && (!best || score > best.score)) {
      best = { name: rule.name, score };
    }
  }

  // Require at least 2 matched signals (weighted) before trusting the guess,
  // so a single stray keyword doesn't flip the selector.
  if (best && best.score >= 1.5) return best.name;
  return null;
}

// ---------------------------------------------------------------------------

type View = "landing" | "have-code" | "build";

export default function CodeWorkspace() {
  const [view, setView] = useState<View>("landing");

  // Shared "have code" workspace state
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("Python");
  const [targetLanguage, setTargetLanguage] = useState("JavaScript");
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");
  const [copied, setCopied] = useState(false);
  const [showLangDropdown, setShowLangDropdown] = useState(false);
  const [showTargetDropdown, setShowTargetDropdown] = useState(false);
  const [error, setError] = useState("");
  const [langAutoDetected, setLangAutoDetected] = useState(false);

  // "Build for me" state
  const [buildPrompt, setBuildPrompt] = useState("");
  const [buildLanguage, setBuildLanguage] = useState("Python");
  const [showBuildLangDropdown, setShowBuildLangDropdown] = useState(false);
  const [buildLoading, setBuildLoading] = useState(false);
  const [buildResult, setBuildResult] = useState<string | null>(null);
  const [buildError, setBuildError] = useState("");

  function handleCodeChange(value: string) {
    setCode(value);
    const detected = detectLanguage(value);
    if (detected && detected !== language) {
      setLanguage(detected);
      setLangAutoDetected(true);
    }
    if (!value.trim()) setLangAutoDetected(false);
  }

  function handleManualLanguageSelect(lang: string) {
    setLanguage(lang);
    setLangAutoDetected(false);
    setShowLangDropdown(false);
  }

  async function runAction(actionId: string) {
    if (!code.trim()) { setError("Paste your code first."); return; }
    setError("");
    setActiveAction(actionId);
    setLoading(true);
    setResult(null);

    const prompts: Record<string, string> = {
      explain: `Explain this ${language} code clearly and concisely. Break it down step by step, explain what each part does, and summarize the overall purpose.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
      debug: `Debug this ${language} code. Identify all bugs, errors, and issues. For each problem: explain what's wrong, why it's a bug, and provide the fixed version of the full code.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
      optimize: `Optimize this ${language} code for performance, readability, and best practices. Show the optimized version with comments explaining what you improved and why.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
      convert: `Convert this ${language} code to ${targetLanguage}. Maintain the same logic and functionality. Provide the complete converted code with any necessary notes about differences.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
      test: `Write comprehensive unit tests for this ${language} code. Cover edge cases, happy paths, and error cases. Use the appropriate testing framework for ${language}.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
      comment: `Add clear, professional comments and documentation to this ${language} code. Include function/class docstrings, inline comments for complex logic, and parameter descriptions.\n\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``,
    };

    try {
      const token = localStorage.getItem("levi_token");
      const res = await fetch("http://127.0.0.1:8000/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: prompts[actionId] }),
      });
      const data = await res.json();
      setResult(data.response || "No response received.");
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function runCustomPrompt() {
    if (!customPrompt.trim()) return;
    if (!code.trim()) { setError("Paste your code first."); return; }
    setError("");
    setActiveAction("custom");
    setLoading(true);
    setResult(null);

    const prompt = `${customPrompt}\n\nHere is the ${language} code:\n\`\`\`${language.toLowerCase()}\n${code}\n\`\`\``;

    try {
      const token = localStorage.getItem("levi_token");
      const res = await fetch("http://127.0.0.1:8000/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: prompt }),
      });
      const data = await res.json();
      setResult(data.response || "No response received.");
      setCustomPrompt("");
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function runBuild() {
    if (!buildPrompt.trim()) { setBuildError("Describe what you want Levi to build."); return; }
    setBuildError("");
    setBuildLoading(true);
    setBuildResult(null);

    const prompt = `Write complete, working ${buildLanguage} code for the following request. Return the full code in a single fenced code block, followed by a short explanation of how it works.\n\nRequest: ${buildPrompt}`;

    try {
      const token = localStorage.getItem("levi_token");
      const res = await fetch("http://127.0.0.1:8000/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: prompt }),
      });
      const data = await res.json();
      setBuildResult(data.response || "No response received.");
    } catch {
      setBuildError("Something went wrong. Please try again.");
    } finally {
      setBuildLoading(false);
    }
  }

  function openBuildResultInWorkspace() {
    if (!buildResult) return;
    const match = buildResult.match(/```[\w-]*\n([\s\S]*?)```/);
    const extracted = match ? match[1].trim() : buildResult.trim();
    setCode(extracted);
    const detected = detectLanguage(extracted) || buildLanguage;
    setLanguage(detected);
    setView("have-code");
    setResult(null);
    setActiveAction(null);
  }

  function copyResult() {
    if (!result) return;
    navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const currentAction = ACTIONS.find((a) => a.id === activeAction);

  // -------------------------------------------------------------------------
  // LANDING — choice screen
  // -------------------------------------------------------------------------
  if (view === "landing") {
    return (
      <div style={{
        height: "100%", display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        padding: "40px 24px", gap: 36,
      }}>
        <div style={{ textAlign: "center" }}>
          <h1 style={{ color: "#F0F4FF", fontSize: 22, fontWeight: 700, margin: 0 }}>
            AI Code Workspace
          </h1>
          <p style={{ color: "#3D4F72", fontSize: 13, marginTop: 6 }}>
            How do you want to start?
          </p>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 20, width: "100%", maxWidth: 640,
        }}>
          <motion.button
            whileHover={{ y: -3 }}
            onClick={() => setView("have-code")}
            style={{
              padding: "28px 22px", textAlign: "left",
              background: "rgba(59,130,246,0.06)",
              border: "1px solid rgba(59,130,246,0.2)",
              borderRadius: 16, cursor: "pointer",
              display: "flex", flexDirection: "column", gap: 14,
            }}
          >
            <div style={{
              width: 42, height: 42, borderRadius: 11,
              background: "rgba(59,130,246,0.12)",
              border: "1px solid rgba(59,130,246,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <FolderInput size={20} color="#3B82F6" />
            </div>
            <div>
              <div style={{ color: "#F0F4FF", fontSize: 15, fontWeight: 700 }}>
                I have code
              </div>
              <div style={{ color: "#8B9CC4", fontSize: 12.5, marginTop: 4, lineHeight: 1.5 }}>
                Paste existing code and explain, debug, optimize, convert, test, or comment it.
              </div>
            </div>
          </motion.button>

          <motion.button
            whileHover={{ y: -3 }}
            onClick={() => setView("build")}
            style={{
              padding: "28px 22px", textAlign: "left",
              background: "rgba(212,175,55,0.06)",
              border: "1px solid rgba(212,175,55,0.2)",
              borderRadius: 16, cursor: "pointer",
              display: "flex", flexDirection: "column", gap: 14,
            }}
          >
            <div style={{
              width: 42, height: 42, borderRadius: 11,
              background: "rgba(212,175,55,0.12)",
              border: "1px solid rgba(212,175,55,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Wand2 size={20} color="#D4AF37" />
            </div>
            <div>
              <div style={{ color: "#F0F4FF", fontSize: 15, fontWeight: 700 }}>
                Build for me
              </div>
              <div style={{ color: "#8B9CC4", fontSize: 12.5, marginTop: 4, lineHeight: 1.5 }}>
                Describe what you want and Levi writes the code from scratch.
              </div>
            </div>
          </motion.button>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // BUILD FOR ME
  // -------------------------------------------------------------------------
  if (view === "build") {
    return (
      <div style={{ height: "100%", overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{
          flexShrink: 0, padding: "20px 28px 16px",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={() => { setView("landing"); setBuildResult(null); setBuildError(""); }}
              style={{
                width: 34, height: 34, borderRadius: 9,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#8B9CC4", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <ArrowLeft size={16} />
            </button>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: "rgba(212,175,55,0.12)",
              border: "1px solid rgba(212,175,55,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Wand2 size={18} color="#D4AF37" />
            </div>
            <div>
              <h1 style={{ color: "#F0F4FF", fontSize: 17, fontWeight: 700, margin: 0 }}>
                Build for me
              </h1>
              <p style={{ color: "#3D4F72", fontSize: 12, margin: 0 }}>
                Describe what you want · Levi writes the code
              </p>
            </div>
          </div>

          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowBuildLangDropdown(!showBuildLangDropdown)}
              onBlur={() => setTimeout(() => setShowBuildLangDropdown(false), 150)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 14px",
                background: "rgba(212,175,55,0.08)",
                border: "1px solid rgba(212,175,55,0.2)",
                borderRadius: 10, color: "#D4AF37",
                fontSize: 13, fontWeight: 600, cursor: "pointer",
              }}
            >
              <Code2 size={13} />
              {buildLanguage}
              <ChevronDown size={12} />
            </button>
            <AnimatePresence>
              {showBuildLangDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    position: "absolute", top: "100%", right: 0,
                    background: "#0D1420", border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 12, marginTop: 4, zIndex: 10,
                    minWidth: 160, maxHeight: 220, overflowY: "auto",
                  }}
                >
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang}
                      onClick={() => { setBuildLanguage(lang); setShowBuildLangDropdown(false); }}
                      style={{
                        width: "100%", padding: "9px 14px",
                        background: buildLanguage === lang ? "rgba(212,175,55,0.1)" : "transparent",
                        border: "none", borderBottom: "1px solid rgba(255,255,255,0.04)",
                        color: buildLanguage === lang ? "#D4AF37" : "#8B9CC4",
                        fontSize: 13, textAlign: "left", cursor: "pointer",
                      }}
                    >
                      {lang}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "1fr 1fr", overflow: "hidden" }}>
          {/* LEFT — description input */}
          <div style={{
            borderRight: "1px solid rgba(255,255,255,0.05)",
            display: "flex", flexDirection: "column", overflow: "hidden",
          }}>
            <div style={{
              padding: "10px 16px", background: "rgba(255,255,255,0.02)",
              borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0,
            }}>
              <span style={{ color: "#3D4F72", fontSize: 12, fontWeight: 600 }}>
                What should Levi build?
              </span>
            </div>

            <textarea
              value={buildPrompt}
              onChange={(e) => setBuildPrompt(e.target.value)}
              placeholder={`Describe what you want in plain English...\n\nExample:\n"A Python function that takes a list of dates and returns them sorted, grouped by month."`}
              style={{
                flex: 1, width: "100%", padding: "16px 20px",
                background: "#060A10", border: "none", outline: "none", resize: "none",
                color: "#C8D4F0", fontSize: 13,
                fontFamily: "'Fira Code', 'Cascadia Code', monospace", lineHeight: 1.7,
              }}
            />

            <div style={{
              flexShrink: 0, padding: "12px 16px",
              borderTop: "1px solid rgba(255,255,255,0.05)",
              background: "rgba(255,255,255,0.01)",
            }}>
              <button
                onClick={runBuild}
                disabled={buildLoading || !buildPrompt.trim()}
                style={{
                  width: "100%", padding: "11px 16px",
                  background: buildPrompt.trim() && !buildLoading
                    ? "linear-gradient(135deg, #D4AF37, #F0C24B)"
                    : "rgba(255,255,255,0.04)",
                  border: "none", borderRadius: 10,
                  color: buildPrompt.trim() && !buildLoading ? "#0A0E14" : "#3D4F72",
                  fontSize: 13, fontWeight: 700,
                  cursor: buildPrompt.trim() && !buildLoading ? "pointer" : "not-allowed",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                }}
              >
                <Sparkles size={14} />
                Generate Code
              </button>
              {buildError && (
                <p style={{ color: "#EF4444", fontSize: 12, marginTop: 8 }}>⚠ {buildError}</p>
              )}
            </div>
          </div>

          {/* RIGHT — generated output */}
          <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{
              padding: "10px 16px", background: "rgba(255,255,255,0.02)",
              borderBottom: "1px solid rgba(255,255,255,0.05)",
              display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0,
            }}>
              <span style={{ color: "#3D4F72", fontSize: 12 }}>Generated code</span>
              {buildResult && (
                <button
                  onClick={openBuildResultInWorkspace}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "6px 12px",
                    background: "rgba(59,130,246,0.1)",
                    border: "1px solid rgba(59,130,246,0.25)",
                    borderRadius: 8, color: "#3B82F6",
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  <FolderInput size={12} />
                  Open in Workspace
                </button>
              )}
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
              {buildLoading && (
                <div style={{
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  height: "100%", gap: 16,
                }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: "50%",
                    background: "rgba(212,175,55,0.12)",
                    border: "1px solid rgba(212,175,55,0.3)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Loader2 size={20} color="#D4AF37" style={{ animation: "spin 1s linear infinite" }} />
                  </div>
                  <p style={{ color: "#3D4F72", fontSize: 13 }}>Levi is writing the code...</p>
                </div>
              )}

              {!buildLoading && !buildResult && (
                <div style={{
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  height: "100%", gap: 12,
                }}>
                  <div style={{
                    width: 56, height: 56, borderRadius: "50%",
                    background: "rgba(212,175,55,0.06)",
                    border: "1px solid rgba(212,175,55,0.15)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <Sparkles size={20} color="#3D4F72" />
                  </div>
                  <p style={{ color: "#3D4F72", fontSize: 13, textAlign: "center" }}>
                    Describe what you want on the left<br />then generate
                  </p>
                </div>
              )}

              {!buildLoading && buildResult && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="markdown-body"
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {buildResult}
                  </ReactMarkdown>
                </motion.div>
              )}
            </div>
          </div>
        </div>

        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // HAVE CODE — existing workspace (unchanged, plus back button + auto-detect)
  // -------------------------------------------------------------------------
  return (
    <div style={{ height: "100%", overflow: "hidden", display: "flex", flexDirection: "column" }}>

      {/* Header */}
      <div style={{
        flexShrink: 0,
        padding: "20px 28px 16px",
        borderBottom: "1px solid rgba(255,255,255,0.05)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => setView("landing")}
            style={{
              width: 34, height: 34, borderRadius: 9,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#8B9CC4", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <ArrowLeft size={16} />
          </button>
          <div style={{
            width: 38, height: 38, borderRadius: 10,
            background: "rgba(59,130,246,0.12)",
            border: "1px solid rgba(59,130,246,0.25)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <FileCode size={18} color="#3B82F6" />
          </div>
          <div>
            <h1 style={{ color: "#F0F4FF", fontSize: 17, fontWeight: 700, margin: 0 }}>
              AI Code Workspace
            </h1>
            <p style={{ color: "#3D4F72", fontSize: 12, margin: 0 }}>
              Paste code · Choose action · Get instant AI analysis
            </p>
          </div>
        </div>

        {/* Language selector */}
        <div style={{ position: "relative" }}>
          <button
            onClick={() => setShowLangDropdown(!showLangDropdown)}
            onBlur={() => setTimeout(() => setShowLangDropdown(false), 150)}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "8px 14px",
              background: "rgba(59,130,246,0.08)",
              border: "1px solid rgba(59,130,246,0.2)",
              borderRadius: 10, color: "#3B82F6",
              fontSize: 13, fontWeight: 600, cursor: "pointer",
            }}
          >
            <Code2 size={13} />
            {language}
            {langAutoDetected && (
              <span style={{
                fontSize: 9.5, fontWeight: 700, letterSpacing: 0.3,
                color: "#22C55E", background: "rgba(34,197,94,0.12)",
                border: "1px solid rgba(34,197,94,0.3)",
                borderRadius: 5, padding: "2px 5px",
              }}>
                AUTO
              </span>
            )}
            <ChevronDown size={12} />
          </button>
          <AnimatePresence>
            {showLangDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                style={{
                  position: "absolute", top: "100%", right: 0,
                  background: "#0D1420", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 12, marginTop: 4, zIndex: 10,
                  minWidth: 160, maxHeight: 220, overflowY: "auto",
                }}
              >
                {LANGUAGES.map((lang) => (
                  <button
                    key={lang}
                    onClick={() => handleManualLanguageSelect(lang)}
                    style={{
                      width: "100%", padding: "9px 14px",
                      background: language === lang ? "rgba(59,130,246,0.1)" : "transparent",
                      border: "none", borderBottom: "1px solid rgba(255,255,255,0.04)",
                      color: language === lang ? "#3B82F6" : "#8B9CC4",
                      fontSize: 13, textAlign: "left", cursor: "pointer",
                    }}
                  >
                    {lang}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Main workspace */}
      <div style={{
        flex: 1, minHeight: 0,
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 0,
        overflow: "hidden",
      }}>

        {/* LEFT — Code input */}
        <div style={{
          borderRight: "1px solid rgba(255,255,255,0.05)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}>
          {/* Editor header */}
          <div style={{
            padding: "10px 16px",
            background: "rgba(255,255,255,0.02)",
            borderBottom: "1px solid rgba(255,255,255,0.05)",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexShrink: 0,
          }}>
            <span style={{ color: "#3D4F72", fontSize: 12, fontWeight: 600 }}>
              {language} · code editor
            </span>
            {code && (
              <button
                onClick={() => { setCode(""); setLangAutoDetected(false); }}
                style={{
                  background: "none", border: "none",
                  color: "#3D4F72", fontSize: 11, cursor: "pointer",
                }}
              >
                Clear
              </button>
            )}
          </div>

          {/* Textarea */}
          <textarea
            value={code}
            onChange={(e) => handleCodeChange(e.target.value)}
            placeholder={`# Paste your code here...\n\nLevi will auto-detect the language.\n\nExample:\ndef hello_world():\n    print("Hello from Levi!")`}
            style={{
              flex: 1, width: "100%", padding: "16px 20px",
              background: "#060A10",
              border: "none", outline: "none", resize: "none",
              color: "#C8D4F0", fontSize: 13,
              fontFamily: "'Fira Code', 'Cascadia Code', monospace",
              lineHeight: 1.7,
            }}
          />

          {/* Action buttons */}
          <div style={{
            flexShrink: 0,
            padding: "12px 16px",
            borderTop: "1px solid rgba(255,255,255,0.05)",
            background: "rgba(255,255,255,0.01)",
          }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              {ACTIONS.map((action) => (
                <button
                  key={action.id}
                  onClick={() => runAction(action.id)}
                  disabled={loading}
                  title={action.description}
                  style={{
                    padding: "9px 8px",
                    background: activeAction === action.id && !loading
                      ? `${action.color}15`
                      : "rgba(255,255,255,0.03)",
                    border: `1px solid ${activeAction === action.id ? action.color + "35" : "rgba(255,255,255,0.06)"}`,
                    borderRadius: 9,
                    color: activeAction === action.id ? action.color : "#8B9CC4",
                    fontSize: 12, fontWeight: 600,
                    cursor: loading ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center",
                    justifyContent: "center", gap: 6,
                    transition: "all 0.15s",
                  }}
                >
                  <span style={{ color: activeAction === action.id ? action.color : "#3D4F72" }}>
                    {action.icon}
                  </span>
                  {action.label}
                </button>
              ))}
            </div>

            {/* Convert target language */}
            {activeAction === "convert" && (
              <div style={{ marginTop: 10, position: "relative" }}>
                <button
                  onClick={() => setShowTargetDropdown(!showTargetDropdown)}
                  onBlur={() => setTimeout(() => setShowTargetDropdown(false), 150)}
                  style={{
                    width: "100%", padding: "8px 12px",
                    background: "rgba(168,85,247,0.08)",
                    border: "1px solid rgba(168,85,247,0.2)",
                    borderRadius: 8, color: "#A855F7",
                    fontSize: 12, cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                  }}
                >
                  Convert to: {targetLanguage}
                  <ChevronDown size={12} />
                </button>
                <AnimatePresence>
                  {showTargetDropdown && (
                    <motion.div
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      style={{
                        position: "absolute", bottom: "100%", left: 0, right: 0,
                        background: "#0D1420", border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 10, marginBottom: 4, zIndex: 10,
                        maxHeight: 180, overflowY: "auto",
                      }}
                    >
                      {LANGUAGES.filter((l) => l !== language).map((lang) => (
                        <button
                          key={lang}
                          onClick={() => { setTargetLanguage(lang); setShowTargetDropdown(false); runAction("convert"); }}
                          style={{
                            width: "100%", padding: "8px 12px",
                            background: "transparent", border: "none",
                            borderBottom: "1px solid rgba(255,255,255,0.04)",
                            color: "#8B9CC4", fontSize: 12,
                            textAlign: "left", cursor: "pointer",
                          }}
                        >
                          {lang}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {error && (
              <p style={{ color: "#EF4444", fontSize: 12, marginTop: 8 }}>⚠ {error}</p>
            )}
          </div>
        </div>

        {/* RIGHT — AI Output */}
        <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Output header */}
          <div style={{
            padding: "10px 16px",
            background: "rgba(255,255,255,0.02)",
            borderBottom: "1px solid rgba(255,255,255,0.05)",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {currentAction && (
                <span style={{ color: currentAction.color, display: "flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600 }}>
                  {currentAction.icon} {currentAction.label} Result
                </span>
              )}
              {!currentAction && (
                <span style={{ color: "#3D4F72", fontSize: 12 }}>AI output</span>
              )}
            </div>
            {result && (
              <button
                onClick={copyResult}
                style={{
                  display: "flex", alignItems: "center", gap: 5,
                  padding: "5px 10px",
                  background: copied ? "rgba(34,197,94,0.1)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${copied ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.06)"}`,
                  borderRadius: 7, color: copied ? "#22C55E" : "#8B9CC4",
                  fontSize: 11, cursor: "pointer",
                }}
              >
                {copied ? <Check size={11} /> : <Copy size={11} />}
                {copied ? "Copied!" : "Copy"}
              </button>
            )}
          </div>

          {/* Output content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
            {loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  height: "100%", gap: 16,
                }}
              >
                <div style={{
                  width: 48, height: 48, borderRadius: "50%",
                  background: `${currentAction?.color || "#3B82F6"}12`,
                  border: `1px solid ${currentAction?.color || "#3B82F6"}30`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Loader2 size={20} color={currentAction?.color || "#3B82F6"}
                    style={{ animation: "spin 1s linear infinite" }} />
                </div>
                <p style={{ color: "#3D4F72", fontSize: 13 }}>
                  Levi is {activeAction === "debug" ? "finding bugs" : activeAction === "explain" ? "analyzing" : activeAction === "optimize" ? "optimizing" : "working"}...
                </p>
              </motion.div>
            )}

            {!loading && !result && (
              <div style={{
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                height: "100%", gap: 12,
              }}>
                <div style={{
                  width: 56, height: 56, borderRadius: "50%",
                  background: "rgba(59,130,246,0.06)",
                  border: "1px solid rgba(59,130,246,0.12)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Play size={20} color="#3D4F72" />
                </div>
                <p style={{ color: "#3D4F72", fontSize: 13, textAlign: "center" }}>
                  Paste your code on the left<br />then choose an action
                </p>
              </div>
            )}

            {!loading && result && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="markdown-body"
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {result}
                </ReactMarkdown>
              </motion.div>
            )}
          </div>

          {/* Custom prompt bar */}
          <div style={{
            flexShrink: 0,
            padding: "10px 16px",
            borderTop: "1px solid rgba(255,255,255,0.05)",
            background: "rgba(255,255,255,0.01)",
            display: "flex", gap: 8,
          }}>
            <input
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runCustomPrompt()}
              placeholder="Ask anything about this code..."
              style={{
                flex: 1, background: "rgba(6,10,16,0.8)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 10, padding: "9px 14px",
                color: "#F0F4FF", fontSize: 13,
                outline: "none", fontFamily: "Inter, sans-serif",
              }}
            />
            <button
              onClick={runCustomPrompt}
              disabled={loading || !customPrompt.trim()}
              style={{
                padding: "9px 16px",
                background: customPrompt.trim() && !loading
                  ? "linear-gradient(135deg, #0057FF, #3B82F6)"
                  : "rgba(255,255,255,0.04)",
                border: "none", borderRadius: 10,
                color: customPrompt.trim() && !loading ? "white" : "#3D4F72",
                fontSize: 13, fontWeight: 600,
                cursor: customPrompt.trim() && !loading ? "pointer" : "not-allowed",
              }}
            >
              Ask
            </button>
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
