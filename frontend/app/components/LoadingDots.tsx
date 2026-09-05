export default function LoadingDots() {
  return (
    <div className="flex justify-start">
      <div className="bg-slate-800 px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1 items-center">
        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 bg-slate-500 rounded-full animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}