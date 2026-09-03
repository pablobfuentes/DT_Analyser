import { useCallback, useState } from 'react';

interface CsvDropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function CsvDropzone({ onFile, disabled }: CsvDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      const file = e.dataTransfer.files[0];
      if (file) onFile(file);
    },
    [onFile, disabled]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      style={{
        border: '2px dashed #888',
        padding: '3rem',
        textAlign: 'center',
        background: dragOver ? '#eef' : '#fafafa',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
    >
      <p>Drop TradingView CSV here</p>
      <input
        type="file"
        accept=".csv"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
    </div>
  );
}
