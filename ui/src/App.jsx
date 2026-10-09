import { useEffect, useRef, useState } from "react";
import "./App.css";

// Where the FastAPI server runs. Override with VITE_API_URL in ui/.env if needed.
const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

const SUGGESTIONS = [
  "I lost my debit card",
  "How long do I have to dispute a charge?",
  "Can you refund an overdraft fee?",
  "I'd like to talk to a person",
];

// The fake customers from bank_data.py, so anyone trying the demo can verify.
const DEMO_CUSTOMERS = [
  { name: "Maria Chen", dob: "1988-04-12", card: "4821", scenario: "Two accounts and two cards" },
  { name: "James Okafor", dob: "1975-11-03", card: "9034", scenario: "A $649.99 charge he doesn't recognize" },
  { name: "Priya Sharma", dob: "1992-07-25", card: "1167", scenario: "Three accounts, one card already frozen" },
  { name: "Liam Tremblay", dob: "2001-01-30", card: "5580", scenario: "Two recent overdraft fees" },
  { name: "Sofia Rossi", dob: "1964-09-18", card: "7702", scenario: "No accounts and a cancelled card" },
];

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status; // 0 means the server couldn't be reached at all
  }
}

async function postChat(sessionId, message) {
  let res;
  try {
    res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
  } catch {
    throw new ApiError(0, `Can't reach the server at ${API_URL}. Check that it's running, then send again.`);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : null;
    if (res.status === 500) {
      throw new ApiError(500, "The server hit an error. The traceback is in the server terminal.");
    }
    throw new ApiError(res.status, detail ?? `The server returned an error (${res.status}).`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);   // what the customer sees
  const [turns, setTurns] = useState([]);         // what the ledger shows, one entry per reply
  const [verified, setVerified] = useState(false);
  const [escalationId, setEscalationId] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const nextId = useRef(0);
  const inputRef = useRef(null);
  const endRef = useRef(null);

  function addMessage(role, text, tone) {
    nextId.current += 1;
    const message = { id: nextId.current, role, text, tone };
    setMessages((prev) => [...prev, message]);
  }

  function resetConversation() {
    setSessionId(null);
    setMessages([]);
    setTurns([]);
    setVerified(false);
    setEscalationId(null);
    inputRef.current?.focus();
  }

  // Keep the newest message in view
  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "end" });
  }, [messages, loading]);

  async function send(text) {
    const message = text.trim();
    if (!message || loading) return;

    setInput("");
    addMessage("customer", message);
    setLoading(true);

    try {
      let data;
      try {
        data = await postChat(sessionId, message);
      } catch (err) {
        if (err.status !== 404 || !sessionId) throw err;
        // The server restarted and forgot this session, so start a new one and resend.
        addMessage("notice", "The server restarted, so this conversation was reset. Your last message was sent in a new conversation.");
        setTurns([]);
        setVerified(false);
        setEscalationId(null);
        data = await postChat(null, message);
      }

      setSessionId(data.session_id);
      addMessage("agent", data.reply);
      setVerified(data.verified);
      setEscalationId(data.escalation_id);
      setTurns((prev) => [...prev, { n: prev.length + 1, message, events: data.tool_events ?? [] }]);
    } catch (err) {
      addMessage("notice", err.message, "error");
      setInput((current) => current || message); // put the message back so it can be resent
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(input);
    }
  }

  function fillCustomerDetails(customer) {
    setInput(`${customer.name}, ${customer.dob}, card ending ${customer.card}`);
    inputRef.current?.focus();
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="app">
      <main className="chat">
        <header className="chat-header">
          <div className="brand">
            <TideMark />
            <span className="brand-name">Tidewell Bank</span>
            <span className="brand-sub">Support</span>
          </div>
          <button type="button" className="button-quiet" onClick={resetConversation} disabled={isEmpty}>
            New conversation
          </button>
        </header>

        <div className="messages">
          <div className={`messages-inner${isEmpty ? " is-empty" : ""}`} role="log" aria-live="polite" aria-label="Conversation">
            {isEmpty && <Welcome onPick={send} />}
            {messages.map((m) => (
              <Message key={m.id} message={m} />
            ))}
            {loading && <Typing />}
            <div ref={endRef} />
          </div>
        </div>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <div className="composer-inner">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message"
              aria-label="Message"
              autoFocus
            />
            <button type="submit" className="send" disabled={loading || !input.trim()}>
              Send
            </button>
          </div>
          <p className="composer-hint">Enter to send. Shift+Enter for a new line.</p>
        </form>
      </main>

      <Ledger turns={turns} verified={verified} escalationId={escalationId} onUseCustomer={fillCustomerDetails} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat pieces
// ---------------------------------------------------------------------------

function TideMark() {
  return (
    <svg className="tide-mark" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect width="28" height="28" rx="7" fill="#12333A" />
      <path d="M5 13c2.2 0 2.2-3 4.5-3s2.3 3 4.5 3 2.3-3 4.5-3 2.3 3 4.5 3" stroke="#6FC2B5" strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M5 19c2.2 0 2.2-2 4.5-2s2.3 2 4.5 2 2.3-2 4.5-2 2.3 2 4.5 2" stroke="#E6EFEE" strokeOpacity=".55" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function Welcome({ onPick }) {
  return (
    <div className="welcome">
      <h1>How can we help today?</h1>
      <p>
        Ask about your accounts, cards, or fees, or about Tidewell's policies. You'll be asked to verify
        your identity before we share any account details.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" className="suggestion" onClick={() => onPick(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Message({ message }) {
  if (message.role === "customer") {
    return (
      <div className="msg msg-customer">
        <span className="sr-only">You said: </span>
        {message.text}
      </div>
    );
  }
  if (message.role === "agent") {
    return (
      <div className="msg msg-agent">
        <span className="sr-only">Tidewell replied: </span>
        <RichText text={message.text} />
      </div>
    );
  }
  const isError = message.tone === "error";
  return (
    <p className={`notice${isError ? " notice-error" : ""}`} role={isError ? "alert" : undefined}>
      {message.text}
    </p>
  );
}

function Typing() {
  return (
    <div className="typing" role="status">
      <span className="sr-only">The assistant is typing</span>
      <i />
      <i />
      <i />
    </div>
  );
}

// Light formatting for Claude's replies: paragraphs, lists, **bold**, and (Source: ...) citations.
// Built from React elements rather than raw HTML, so replies can never inject markup.
const INLINE = /(\*\*[^*]+\*\*|\(Source:[^)]+\))/g;

function renderInline(text) {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("(Source:")) {
      return (
        <span key={i} className="citation" title="Help center article">
          <BookIcon />
          <span className="sr-only">Source: </span>
          {part.slice(8, -1).trim()}
        </span>
      );
    }
    return part;
  });
}

function RichText({ text }) {
  const blocks = [];
  let list = null;

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      const ordered = /^\s*\d/.test(line);
      if (!list || list.ordered !== ordered) {
        list = { ordered, items: [] };
        blocks.push(list);
      }
      list.items.push(item[1]);
    } else {
      list = null;
      const heading = line.match(/^#{1,4}\s+(.*)$/);
      if (heading) blocks.push({ text: `**${heading[1]}**` });
      else if (line.trim()) blocks.push({ text: line });
    }
  }

  return blocks.map((block, i) => {
    if (block.items) {
      const List = block.ordered ? "ol" : "ul";
      return (
        <List key={i}>
          {block.items.map((it, j) => (
            <li key={j}>{renderInline(it)}</li>
          ))}
        </List>
      );
    }
    return <p key={i}>{renderInline(block.text)}</p>;
  });
}

function BookIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 3.5C2 2.7 2.7 2 3.5 2H7v11H3.5c-.8 0-1.5.4-1.5 1V3.5zM14 3.5C14 2.7 13.3 2 12.5 2H9v11h3.5c.8 0 1.5.4 1.5 1V3.5z" fill="currentColor" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Agent ledger (developer view)
// ---------------------------------------------------------------------------

function Ledger({ turns, verified, escalationId, onUseCustomer }) {
  const bodyRef = useRef(null);

  // Keep the newest turn in view
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length]);

  return (
    <aside className="ledger" aria-label="Agent ledger">
      <div className="ledger-header">
        <h2>Agent ledger</h2>
        <p>What the agent did behind each reply.</p>
        <dl className="status">
          <dt>Identity</dt>
          <dd>
            <span className={`dot${verified ? " on" : ""}`} aria-hidden="true" />
            {verified ? "Verified" : "Not verified"}
          </dd>
          <dt>Escalation</dt>
          <dd className={escalationId ? "escalated" : undefined}>{escalationId ?? "None"}</dd>
        </dl>
      </div>

      <div className="ledger-body" ref={bodyRef}>
        {turns.length === 0 ? (
          <p className="ledger-empty">Tool calls for each reply appear here, with their inputs and results.</p>
        ) : (
          <ol className="turns">
            {turns.map((turn) => (
              <Turn key={turn.n} turn={turn} />
            ))}
          </ol>
        )}
      </div>

      <DemoCustomers onUse={onUseCustomer} />
    </aside>
  );
}

function Turn({ turn }) {
  return (
    <li className="turn">
      <span className="turn-marker" aria-hidden="true">
        {turn.n}
      </span>
      <p className="turn-message">
        <span className="sr-only">Turn {turn.n}: </span>
        {turn.message}
      </p>
      {turn.events.length === 0 ? (
        <p className="turn-empty">No tools used</p>
      ) : (
        <ul className="events">
          {turn.events.map((event, i) => (
            <ToolEvent key={i} event={event} />
          ))}
        </ul>
      )}
    </li>
  );
}

function ToolEvent({ event }) {
  return (
    <li>
      <details className={`event${event.is_error ? " is-error" : ""}`}>
        <summary>
          <span className="chev" aria-hidden="true" />
          <span className="tool-name">{event.name}</span>
          <span className={event.is_error ? "status-error" : "status-ok"}>{event.is_error ? "Error" : "OK"}</span>
        </summary>
        <div className="event-body">
          <h3>Input</h3>
          <pre>{JSON.stringify(event.input, null, 2)}</pre>
          <h3>Result</h3>
          <pre>{event.result}</pre>
        </div>
      </details>
    </li>
  );
}

function DemoCustomers({ onUse }) {
  return (
    <details className="demo">
      <summary>Demo customers</summary>
      <p>Fake customers for testing. Choose one to fill in their verification details.</p>
      <ul className="demo-list">
        {DEMO_CUSTOMERS.map((c) => (
          <li key={c.card}>
            <button type="button" onClick={() => onUse(c)}>
              <span className="demo-name">{c.name}</span>
              <span className="demo-meta">{c.scenario}</span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
