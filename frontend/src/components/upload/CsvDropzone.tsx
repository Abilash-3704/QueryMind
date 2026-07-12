import { motion } from "framer-motion";
import { useRef, useState } from "react";

import { useQuerySession } from "../../hooks/useQuerySession";
import { ANIMATION } from "../../lib/motion";
import { Button } from "../ui/Button";

export function CsvDropzone() {
  const { upload, isUploading } = useQuerySession();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setSelectedFiles(Array.from(files));
    setError(null);
  };

  const handleSubmit = async () => {
    if (selectedFiles.length === 0) return;
    setError(null);
    try {
      await upload(selectedFiles);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{
        opacity: 1,
        y: 0,
        boxShadow: dragActive
          ? "0 0 28px 0 rgba(0,229,255,0.35)"
          : [
              "0 0 0px 0 rgba(0,229,255,0)",
              "0 0 22px 0 rgba(0,229,255,0.18)",
              "0 0 0px 0 rgba(0,229,255,0)",
            ],
      }}
      transition={{
        opacity: { duration: ANIMATION.slow, ease: ANIMATION.ease },
        y: { duration: ANIMATION.slow, ease: ANIMATION.ease },
        boxShadow: dragActive
          ? { duration: ANIMATION.fast }
          : { duration: 3.5, repeat: Infinity, ease: "easeInOut" },
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragActive(false);
        handleFiles(e.dataTransfer.files);
      }}
      className={`mx-auto mt-24 max-w-md rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        dragActive ? "border-accent bg-accent/5" : "border-border"
      }`}
    >
      <h2 className="font-sans text-lg font-semibold">Upload a CSV to get started</h2>
      <p className="mt-1 font-sans text-sm text-white/60">
        Drag and drop a file here, or choose one below.
      </p>

      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        multiple
        onChange={(e) => handleFiles(e.target.files)}
        className="hidden"
      />

      <div className="mt-4">
        <Button variant="ghost" onClick={() => inputRef.current?.click()}>
          Browse files…
        </Button>
      </div>

      {selectedFiles.length > 0 && (
        <ul className="mt-2 font-mono text-xs text-white/70">
          {selectedFiles.map((f) => (
            <li key={f.name}>{f.name}</li>
          ))}
        </ul>
      )}

      <div className="mt-4">
        <Button
          variant="primary"
          onClick={handleSubmit}
          disabled={selectedFiles.length === 0 || isUploading}
        >
          {isUploading ? "Uploading…" : "Upload"}
        </Button>
      </div>

      {error && <p className="mt-2 font-sans text-sm text-red-400">{error}</p>}
    </motion.div>
  );
}
