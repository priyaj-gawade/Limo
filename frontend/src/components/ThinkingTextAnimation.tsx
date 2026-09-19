import React, { useState, useEffect } from 'react';

const THINKING_PHASES = [
  'Thinking...',
  'Searching knowledge...',
  'Solving & connecting ideas...',
  'Weaving response...',
  'Composing output...',
  'Shaping deliverable...'
];

interface ThinkingTextAnimationProps {
  onPhaseChange?: (phaseIndex: number, phaseText: string) => void;
  className?: string;
}

export const ThinkingTextAnimation: React.FC<ThinkingTextAnimationProps> = ({
  onPhaseChange,
  className = ''
}) => {
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [isFading, setIsFading] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setIsFading(true);
      setTimeout(() => {
        setPhaseIndex((prev) => {
          const next = (prev + 1) % THINKING_PHASES.length;
          if (onPhaseChange) {
            onPhaseChange(next, THINKING_PHASES[next]);
          }
          return next;
        });
        setIsFading(false);
      }, 200);
    }, 2500);

    return () => clearInterval(interval);
  }, [onPhaseChange]);

  const currentText = THINKING_PHASES[phaseIndex];

  return (
    <div
      className={`thinking-text-stream ${className}`}
      aria-live="polite"
      role="status"
    >
      <span
        className={`thinking-text-shimmer ${isFading ? 'phase-fading' : 'phase-visible'}`}
      >
        {currentText}
      </span>
    </div>
  );
};
