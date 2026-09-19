import React, { useState, useEffect, useRef } from 'react';
import { Blobatar } from '@blobatar/react';
import {
  idle,
  happy,
  thinking,
  smug,
  wink,
  surprised,
  mad,
  sad,
  unsure,
  love,
  scared,
  shy,
  sick,
  sleepy
} from 'blobatar/expression';
import 'blobatar/motion.css';

const EXPRESSION_MAP = {
  idle,
  happy,
  thinking,
  smug,
  wink,
  surprised,
  mad,
  sad,
  unsure,
  love,
  scared,
  shy,
  sick,
  sleepy,
};

export type MascotEmotion = keyof typeof EXPRESSION_MAP;

interface LimoMascotProps {
  size?: number;
  isGenerating?: boolean;
  emotion?: MascotEmotion;
  interactive?: boolean;
  className?: string;
  title?: string;
}

export const LimoMascot: React.FC<LimoMascotProps> = ({
  size = 42,
  isGenerating = false,
  emotion,
  interactive = true,
  className = '',
  title = 'Limo'
}) => {
  const [currentEmotion, setCurrentEmotion] = useState<MascotEmotion>(() => {
    if (isGenerating) return 'thinking';
    return emotion || 'happy';
  });

  const gestureTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Synchronize when isGenerating or emotion prop changes
  useEffect(() => {
    if (isGenerating) {
      setCurrentEmotion('thinking');
      // During active generation, cycle between thinking, surprised (insight!), and smug (solved!)
      const thinkingCycle: MascotEmotion[] = ['thinking', 'thinking', 'surprised', 'thinking', 'smug'];
      let step = 0;

      const interval = setInterval(() => {
        step = (step + 1) % thinkingCycle.length;
        setCurrentEmotion(thinkingCycle[step]);
      }, 3200);

      return () => clearInterval(interval);
    } else {
      // When generation ends, reward with happy or smug
      setCurrentEmotion(emotion || 'happy');

      // Spontaneous autonomous idle life: occasionally wink or perk every 15-20s
      const scheduleIdleGesture = () => {
        const nextDelay = 14000 + Math.random() * 8000;
        gestureTimerRef.current = setTimeout(() => {
          const idleGestures: MascotEmotion[] = ['wink', 'smug', 'happy', 'surprised'];
          const picked = idleGestures[Math.floor(Math.random() * idleGestures.length)];
          setCurrentEmotion(picked);

          // Return to resting pose after 1.8s
          gestureTimerRef.current = setTimeout(() => {
            setCurrentEmotion(emotion || 'happy');
            scheduleIdleGesture();
          }, 1800);
        }, nextDelay);
      };

      scheduleIdleGesture();

      return () => {
        if (gestureTimerRef.current) clearTimeout(gestureTimerRef.current);
      };
    }
  }, [isGenerating, emotion]);

  // Playful interaction on click
  const handleClick = () => {
    if (!interactive) return;
    const reactions: MascotEmotion[] = ['wink', 'surprised', 'love', 'smug', 'mad', 'happy'];
    const nextReaction = reactions[Math.floor(Math.random() * reactions.length)];
    setCurrentEmotion(nextReaction);

    if (gestureTimerRef.current) clearTimeout(gestureTimerRef.current);
    gestureTimerRef.current = setTimeout(() => {
      setCurrentEmotion(isGenerating ? 'thinking' : emotion || 'happy');
    }, 2000);
  };

  const resolvedExpression = EXPRESSION_MAP[currentEmotion] || happy;

  return (
    <div
      className={`limo-mascot-container ${className} ${isGenerating ? 'is-thinking' : ''}`}
      onClick={handleClick}
      title={title}
      style={{ width: size, height: size }}
    >
      <Blobatar
        name="Limo"
        traits={{ shape: 0.65 }}
        hue={225}
        expression={resolvedExpression}
        animate="always"
        size={size}
      />
    </div>
  );
};
