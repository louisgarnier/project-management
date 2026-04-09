import type { Call } from "@/types";

type Props = {
  call: Call;
  stageColor: string;
};

export default function CallCard({ call, stageColor }: Props) {
  return (
    <div
      className="bg-[#f4f5f7] rounded p-2 mb-1.5 border-l-[3px]"
      style={{ borderLeftColor: stageColor }}
    >
      <p className="text-[11px] font-medium text-[#172b4d] leading-snug">
        {call.title}
      </p>
      <p className="text-[10px] text-[#5e6c84] mt-1">
        {new Date(call.created_at).toLocaleDateString()}
      </p>
    </div>
  );
}
