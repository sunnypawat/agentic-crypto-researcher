import { motion } from "framer-motion";

export function Robot({
  mood,
  message,
}: {
  mood: "idle" | "thinking" | "tools" | "speaking";
  message: string;
}) {
  const eyeBlink =
    mood === "idle"
      ? {
          scaleY: [1, 1, 0.1, 1, 1],
          transition: { duration: 3.2, repeat: Infinity },
        }
      : {
          scaleY: [1, 0.2, 1],
          transition: { duration: 0.9, repeat: Infinity },
        };

  const bob =
    mood === "speaking"
      ? { y: [0, -2, 0], transition: { duration: 0.8, repeat: Infinity } }
      : mood === "thinking" || mood === "tools"
      ? { y: [0, -3, 0], transition: { duration: 1.0, repeat: Infinity } }
      : { y: [0, -1, 0], transition: { duration: 1.6, repeat: Infinity } };

  return (
    <div className="robotWrap">
      <motion.div className="robot" animate={bob}>
        <svg
          width="120"
          height="120"
          viewBox="0 0 120 120"
          className="robotSvg"
          aria-hidden
        >
          <defs>
            <linearGradient id="rb_shell" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="rgba(124,58,237,0.55)" />
              <stop offset="1" stopColor="rgba(6,182,212,0.35)" />
            </linearGradient>
            <linearGradient id="rb_glass" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="rgba(255,255,255,0.18)" />
              <stop offset="1" stopColor="rgba(255,255,255,0.06)" />
            </linearGradient>
            <filter id="rb_glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* antenna */}
          <circle
            cx="60"
            cy="12"
            r="6"
            fill="rgba(6,182,212,0.9)"
            filter="url(#rb_glow)"
          />
          <rect
            x="57.5"
            y="16"
            width="5"
            height="14"
            rx="2.5"
            fill="rgba(255,255,255,0.12)"
          />

          {/* head */}
          <rect
            x="20"
            y="26"
            width="80"
            height="60"
            rx="18"
            fill="url(#rb_shell)"
            stroke="rgba(255,255,255,0.18)"
          />
          {/* glass panel */}
          <rect
            x="28"
            y="34"
            width="64"
            height="40"
            rx="14"
            fill="url(#rb_glass)"
            stroke="rgba(255,255,255,0.16)"
          />

          {/* eyes */}
          <g transform="translate(0,0)">
            <motion.rect
              x="40"
              y="44"
              width="12"
              height="10"
              rx="5"
              fill="rgba(232,236,246,0.9)"
              animate={eyeBlink as any}
              style={{ transformOrigin: "46px 49px" }}
            />
            <motion.rect
              x="68"
              y="44"
              width="12"
              height="10"
              rx="5"
              fill="rgba(232,236,246,0.9)"
              animate={eyeBlink as any}
              style={{ transformOrigin: "74px 49px" }}
            />
          </g>

          {/* mouth */}
          <rect
            x="44"
            y="60"
            width="32"
            height={mood === "speaking" ? 8 : 5}
            rx="4"
            fill={
              mood === "speaking"
                ? "rgba(6,182,212,0.85)"
                : "rgba(232,236,246,0.45)"
            }
          />

          {/* body */}
          <rect
            x="32"
            y="94"
            width="56"
            height="22"
            rx="12"
            fill="rgba(255,255,255,0.06)"
            stroke="rgba(255,255,255,0.14)"
          />
          <circle cx="46" cy="105" r="3" fill="rgba(255,255,255,0.18)" />
          <circle cx="60" cy="105" r="3" fill="rgba(255,255,255,0.18)" />
          <circle cx="74" cy="105" r="3" fill="rgba(255,255,255,0.18)" />
        </svg>
      </motion.div>
      <div className="robotBubble">
        <div className="robotBubbleTitle">
          {mood === "tools"
            ? "Using tools"
            : mood === "thinking"
            ? "Thinking"
            : mood === "speaking"
            ? "Explaining"
            : "Ready"}
        </div>
        <div className="robotBubbleText">{message}</div>
      </div>
    </div>
  );
}
