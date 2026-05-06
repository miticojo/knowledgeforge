import {
  AbsoluteFill,
  Img,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SCENES, FPS } from "./scenes";

const BG = "#020617"; // matches app dark theme --background
const FG = "#e5e7eb";
const ACCENT_ORANGE = "#f97316";
const ACCENT_BLUE = "#3b82f6";
const PANEL = "rgba(2, 6, 23, 0.78)";

function SceneSlide({
  image,
  title,
  body,
  durationFrames,
  index,
  total,
}: {
  image: string;
  title: string;
  body: string;
  durationFrames: number;
  index: number;
  total: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Image: gentle Ken-Burns zoom (1.0 -> 1.06) + cross-fade in/out
  const zoom = interpolate(frame, [0, durationFrames], [1.0, 1.06], {
    extrapolateRight: "clamp",
  });
  const fadeIn = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(
    frame,
    [durationFrames - 12, durationFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const opacity = Math.min(fadeIn, fadeOut);

  // Caption slides in from below + fades
  const captionLift = spring({
    frame: frame - 6,
    fps,
    config: { damping: 18, stiffness: 90 },
  });
  const captionTranslate = interpolate(captionLift, [0, 1], [40, 0]);
  const captionOpacity = interpolate(captionLift, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{ background: BG }}>
      <AbsoluteFill
        style={{
          opacity,
          transform: `scale(${zoom})`,
          transformOrigin: "center 35%",
        }}
      >
        <Img
          src={staticFile(image)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "top center",
          }}
        />
      </AbsoluteFill>

      {/* Soft gradient over the bottom for caption legibility */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(to top, rgba(2,6,23,0.92) 0%, rgba(2,6,23,0.55) 35%, transparent 60%)",
          pointerEvents: "none",
        }}
      />

      {/* Caption block */}
      <div
        style={{
          position: "absolute",
          left: 60,
          right: 60,
          bottom: 60,
          color: FG,
          fontFamily: "Inter, sans-serif",
          opacity: captionOpacity,
          transform: `translateY(${captionTranslate}px)`,
        }}
      >
        <div
          style={{
            fontSize: 14,
            color: ACCENT_ORANGE,
            letterSpacing: 2,
            fontWeight: 600,
            textTransform: "uppercase",
            marginBottom: 10,
          }}
        >
          Step {index + 1} / {total}
        </div>
        <div
          style={{
            fontSize: 44,
            fontWeight: 700,
            marginBottom: 14,
            color: "#ffffff",
            letterSpacing: -0.5,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 22,
            lineHeight: 1.45,
            maxWidth: 1200,
            color: "rgba(229,231,235,0.92)",
            background: PANEL,
            padding: "16px 22px",
            borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.08)",
            backdropFilter: "blur(8px)",
          }}
        >
          {body}
        </div>
      </div>

      {/* Progress bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 4,
          background: "rgba(255,255,255,0.06)",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${((index + frame / durationFrames) / total) * 100}%`,
            background: `linear-gradient(90deg, ${ACCENT_ORANGE}, ${ACCENT_BLUE})`,
            transition: "width 200ms linear",
          }}
        />
      </div>
    </AbsoluteFill>
  );
}

function TitleCard() {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 25], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(frame, [60, 75], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const opacity = Math.min(fadeIn, fadeOut);
  const scale = spring({ frame, fps: FPS, config: { damping: 14, stiffness: 80 } });
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center" }}>
      <div style={{ opacity, transform: `scale(${0.92 + scale * 0.08})`, textAlign: "center", color: FG, fontFamily: "Inter, sans-serif" }}>
        <div style={{ fontSize: 18, color: ACCENT_ORANGE, letterSpacing: 6, fontWeight: 600, marginBottom: 18 }}>
          A WALKTHROUGH
        </div>
        <div style={{ fontSize: 96, fontWeight: 800, color: "#ffffff", letterSpacing: -2 }}>
          Knowledge<span style={{ color: ACCENT_ORANGE }}>Forge</span>
        </div>
        <div style={{ fontSize: 24, marginTop: 22, color: "rgba(229,231,235,0.7)" }}>
          Documents and code, one navigable knowledge graph
        </div>
      </div>
    </AbsoluteFill>
  );
}

function EndCard() {
  const frame = useCurrentFrame();
  const fadeIn = interpolate(frame, [0, 25], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center", opacity: fadeIn, color: FG, fontFamily: "Inter, sans-serif" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 60, fontWeight: 800, color: "#ffffff", letterSpacing: -1 }}>
          Try it locally
        </div>
        <div style={{ marginTop: 24, fontSize: 22, color: "rgba(229,231,235,0.85)", fontFamily: "monospace" }}>
          docker compose -f docker-compose.demo.yml up -d
        </div>
        <div style={{ marginTop: 12, fontSize: 22, color: "rgba(229,231,235,0.85)", fontFamily: "monospace" }}>
          ./demo/scripts/seed.sh
        </div>
        <div style={{ marginTop: 36, fontSize: 18, color: "rgba(229,231,235,0.55)" }}>
          github.com / miticojo-labs / knowledgeforge
        </div>
      </div>
    </AbsoluteFill>
  );
}

export const Walkthrough: React.FC = () => {
  const TITLE_FRAMES = 75;   // ~2.5s
  const END_FRAMES = 90;     // ~3s
  let cursor = 0;

  const total = SCENES.length;

  return (
    <AbsoluteFill style={{ background: BG }}>
      <Sequence from={cursor} durationInFrames={TITLE_FRAMES}>
        <TitleCard />
      </Sequence>
      {(() => {
        cursor += TITLE_FRAMES;
        return null;
      })()}

      {SCENES.map((s, i) => {
        const frames = Math.round(s.duration * FPS);
        const node = (
          <Sequence key={s.image} from={cursor} durationInFrames={frames}>
            <SceneSlide
              image={s.image}
              title={s.title}
              body={s.body}
              durationFrames={frames}
              index={i}
              total={total}
            />
          </Sequence>
        );
        cursor += frames;
        return node;
      })}

      <Sequence from={cursor} durationInFrames={END_FRAMES}>
        <EndCard />
      </Sequence>
    </AbsoluteFill>
  );
};
