import { useRef } from "react";
import { Paperclip, Loader2 } from "lucide-react";
import { useDocumentStore } from "../stores/documentStore";

interface DocumentUploadButtonProps {
  onFileSelect?: (file: File) => void;
}

export default function DocumentUploadButton({ onFileSelect }: DocumentUploadButtonProps) {
  const uploading = useDocumentStore((s) => s.uploading);
  const uploadDocument = useDocumentStore((s) => s.uploadDocument);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (onFileSelect) {
      onFileSelect(file);
    } else {
      await uploadDocument(file);
    }
    // Reset input so same file can be re-uploaded
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png"
        onChange={handleFileChange}
        className="hidden"
      />
      <button
        type="button"
        onClick={handleClick}
        disabled={uploading}
        className="p-2 rounded-lg text-[#6b6b8a] hover:text-[#e0e0e0] hover:bg-[#2d2d5e] transition-colors disabled:opacity-50"
        title="Upload lab results (PDF)"
      >
        {uploading ? (
          <Loader2 className="w-5 h-5 animate-spin" />
        ) : (
          <Paperclip className="w-5 h-5" />
        )}
      </button>
    </>
  );
}
