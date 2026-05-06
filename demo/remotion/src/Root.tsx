import { Composition } from "remotion";
import { Walkthrough } from "./Walkthrough";
import { SCENES, FPS, WIDTH, HEIGHT } from "./scenes";

export const RemotionRoot: React.FC = () => {
  // total = title (2.5s) + scenes + end (3s)
  const titleFrames = 75;
  const endFrames = 90;
  const sceneFrames = SCENES.reduce((acc, s) => acc + Math.round(s.duration * FPS), 0);
  const totalFrames = titleFrames + sceneFrames + endFrames;

  return (
    <>
      <Composition
        id="Walkthrough"
        component={Walkthrough}
        durationInFrames={totalFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
