import { create } from "zustand";

import type { AgentStep, ChartSpec, TableInfo } from "../api/client";

export interface ChatMessage {
  id: string;
  question: string;
  answer?: string;
  sql?: string | null;
  result?: Record<string, unknown>[] | null;
  chartSpec?: ChartSpec | null;
  trace?: AgentStep[];
  retryCount?: number;
  clarificationQuestion?: string | null;
  status: "pending" | "done" | "error";
  error?: string;
}

interface SessionState {
  sessionId: string | null;
  tables: TableInfo[];
  messages: ChatMessage[];
  isUploading: boolean;
  isQuerying: boolean;

  setSession: (sessionId: string, tables: TableInfo[]) => void;
  clearSession: () => void;
  setUploading: (uploading: boolean) => void;
  setQuerying: (querying: boolean) => void;
  addMessage: (msg: ChatMessage) => void;
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  tables: [],
  messages: [],
  isUploading: false,
  isQuerying: false,

  setSession: (sessionId, tables) => set({ sessionId, tables }),
  clearSession: () => set({ sessionId: null, tables: [], messages: [] }),
  setUploading: (uploading) => set({ isUploading: uploading }),
  setQuerying: (querying) => set({ isQuerying: querying }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
}));
