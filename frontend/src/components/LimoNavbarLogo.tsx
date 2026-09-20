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

const EXPRESSION_ROSTER = {
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
};

export type NavbarMascotEmotion = keyof typeof EXPRESSION_ROSTER;

const ALL_EMOTIONS: NavbarMascotEmotion[] = [
  'idle',
  'happy',
  'wink',
  'thinking',
  'smug',
  'surprised',
  'sleepy',
  'love',
  'shy',
  'unsure',
  'scared',
  'happy',
  'wink',
  'mad',
  'sick',
  'sad'
];

interface LimoNavbarLogoProps {
  size?: number;
  className?: string;
  title?: string;
  onClick?: (e: React.MouseEvent) => void;
}

export const LimoNavbarLogo: React.FC<LimoNavbarLogoProps> = ({
  size = 28,
  className = '',
  title = 'Limo AI',
  onClick
}) => {
  const [currentEmotion, setCurrentEmotion] = useState<NavbarMascotEmotion>('idle');
  const [isHovered, setIsHovered] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const resetTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const scheduleNextRhythm = () => {
      // 3 to 5 seconds rhythm
      const delay = 3000 + Math.random() * 2000;
      timerRef.current = setTimeout(() => {
        if (!isHovered) {
          const randomIndex = Math.floor(Math.random() * ALL_EMOTIONS.length);
          const nextEmotion = ALL_EMOTIONS[randomIndex];
          setCurrentEmotion(nextEmotion);

          // For expressive transient emotions, return to calm baseline after 1.5s
          if (['wink', 'surprised', 'scared', 'unsure', 'mad', 'sick', 'sad'].includes(nextEmotion)) {
            resetTimerRef.current = setTimeout(() => {
              setCurrentEmotion('idle');
            }, 1500);
          }
        }
        scheduleNextRhythm();
      }, delay);
    };

    scheduleNextRhythm();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    };
  }, [isHovered]);

  const handleMouseEnter = () => {
    setIsHovered(true);
    const hoverEmotions: NavbarMascotEmotion[] = ['wink', 'surprised', 'smug', 'happy'];
    const chosen = hoverEmotions[Math.floor(Math.random() * hoverEmotions.length)];
    setCurrentEmotion(chosen);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
    setCurrentEmotion('idle');
  };

  const handleClick = (e: React.MouseEvent) => {
    const clickEmotions: NavbarMascotEmotion[] = ['love', 'smug', 'wink', 'surprised'];
    const chosen = clickEmotions[Math.floor(Math.random() * clickEmotions.length)];
    setCurrentEmotion(chosen);

    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    resetTimerRef.current = setTimeout(() => {
      setCurrentEmotion('idle');
    }, 1800);

    if (onClick) {
      onClick(e);
    }
  };

  const expressionDef = EXPRESSION_ROSTER[currentEmotion] || idle;

  return (
    <div
      className={`limo-navbar-logo ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      title={title}
      style={{
        width: size,
        height: size,
        minWidth: size,
        minHeight: size,
        maxWidth: size,
        maxHeight: size,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'transparent',
        flexShrink: 0,
        cursor: 'pointer',
        userSelect: 'none',
        lineHeight: 0
      }}
    >
      <Blobatar
        name="Limo"
        traits={{ shape: 0.65 }}
        hue={225}
        expression={expressionDef}
        animate="always"
        size={size}
      />
    </div>
  );
};
