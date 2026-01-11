import { memo, useMemo } from "react";

type Point = { t: number; p: number };

export const Sparkline = memo(function Sparkline({
  points,
  width = 160,
  height = 44,
}: {
  points: Point[];
  width?: number;
  height?: number;
}) {
  const d = useMemo(() => {
    if (!points || points.length < 2) return "";
    const ps = points.map((x) => x.p);
    const min = Math.min(...ps);
    const max = Math.max(...ps);
    const range = Math.max(1e-9, max - min);

    const stepX = width / (points.length - 1);
    const path = points
      .map((pt, i) => {
        const x = i * stepX;
        const y = height - ((pt.p - min) / range) * (height - 6) - 3;
        return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
    return path;
  }, [points, width, height]);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path
        d={d}
        fill="none"
        stroke="rgba(6, 182, 212, 0.9)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
});
