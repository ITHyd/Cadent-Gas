import { useRef, useState } from 'react';

const UploadInput = ({ uploadData, onUpload }) => {
  const fileInputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (selectedFile) {
      setUploading(true);
      await onUpload(selectedFile);
      setUploading(false);
      setSelectedFile(null);
    }
  };

  const handleSkip = () => {
    if (!uploadData.required) {
      onUpload(null); // Skip upload
    }
  };

  const getAcceptString = () => {
    if (uploadData.upload_type === 'image') return 'image/*';
    if (uploadData.upload_type === 'audio') return 'audio/*';
    if (uploadData.upload_type === 'video') return 'video/*';
    return '*/*';
  };

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50/80 p-6 text-center">
        <input
          ref={fileInputRef}
          type="file"
          accept={getAcceptString()}
          onChange={handleFileSelect}
          className="hidden"
        />
        
        {!selectedFile ? (
          <div>
            <svg
              className="mx-auto h-12 w-12 text-slate-400"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="mt-2 text-sm text-slate-600">{uploadData.prompt}</p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="btn-primary mt-4"
            >
              Choose File
            </button>
          </div>
        ) : (
          <div>
            <p className="text-sm font-semibold text-slate-700">Selected: {selectedFile.name}</p>
            <p className="text-xs text-slate-500">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
            <div className="mt-4 flex justify-center gap-3">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="btn-base bg-emerald-600 text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
              <button
                onClick={() => setSelectedFile(null)}
                className="btn-secondary"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {!uploadData.required && (
        <button
          onClick={handleSkip}
          className="w-full text-sm font-medium text-slate-600 underline decoration-slate-400 underline-offset-2 hover:text-slate-900"
        >
          Skip this step
        </button>
      )}
    </div>
  );
};

export default UploadInput;
