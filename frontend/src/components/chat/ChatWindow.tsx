import { useState } from "react";

import { useQuerySession } from "../../hooks/useQuerySession";
import { Button } from "../ui/Button";
import { MessageBubble } from "./MessageBubble";

export function ChatWindow() {
  const { messages, ask, isQuerying } = useQuerySession();
  const [input, setInput] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question) return;
    setInput("");
    await ask(question);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden p-4">
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 && (
          <p className="font-sans text-sm text-white/40">
            Ask a question about your data.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      <form onSubmit={handleSubmit} className="mt-2 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={isQuerying}
          className="flex-1 rounded-md border border-border bg-panel px-3 py-2 font-sans text-sm text-white placeholder:text-white/30 focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <Button variant="primary" type="submit" disabled={isQuerying || !input.trim()}>
          {isQuerying ? "Asking…" : "Ask"}
        </Button>
      </form>
    </div>
  );
}
