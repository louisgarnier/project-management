export default function TopNav() {
  return (
    <nav className="bg-[#0052cc] h-11 flex items-center px-4 gap-3 flex-shrink-0 z-10">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 bg-white rounded flex items-center justify-center text-[10px] font-bold text-[#0052cc] flex-shrink-0">
          CT
        </div>
        <span className="text-white font-semibold text-[13px]">Call Tracker</span>
      </div>
      <div className="flex-1" />
      <div className="w-7 h-7 rounded-full bg-[#0065ff] flex items-center justify-center text-white text-[11px] font-semibold flex-shrink-0">
        LG
      </div>
    </nav>
  );
}
