import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Blobatar } from '@blobatar/react';
import {
  idle,
  happy,
  thinking,
  smug,
  wink,
  surprised,
  love,
  shy,
  unsure,
  scared
} from 'blobatar/expression';
import 'blobatar/motion.css';

const MASCOT_EXPRESSIONS = {
  idle,
  happy,
  thinking,
  smug,
  wink,
  surprised,
  love,
  shy,
  unsure,
  scared
};

export type MascotEmotion = keyof typeof MASCOT_EXPRESSIONS;

interface InteractiveLimoMascotProps {
  size?: number;
  className?: string;
}

export const InteractiveLimoMascot: React.FC<InteractiveLimoMascotProps> = ({
  size = 190,
  className = ''
}) => {
  const [currentEmotion, setCurrentEmotion] = useState<MascotEmotion>('happy');
  const [transformStyle, setTransformStyle] = useState<string>('perspective(600px) rotateX(0deg) rotateY(0deg)');
  const [shadowOffset, setShadowOffset] = useState<{ x: number; y: number }>({ x: 0, y: 15 });
  const [isPoked, setIsPoked] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const idleTimerRef = useRef<NodeJS.Timeout | null>(null);
  const resetTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isInteractingRef = useRef<boolean>(false);

  // Periodic lively expressions when idle
  useEffect(() => {
    const cycleIdleEmotions = () => {
      const delay = 3500 + Math.random() * 2500;
      idleTimerRef.current = setTimeout(() => {
        if (!isInteractingRef.current) {
          const idlePool: MascotEmotion[] = ['wink', 'happy', 'thinking', 'smug', 'shy'];
          const next = idlePool[Math.floor(Math.random() * idlePool.length)];
          setCurrentEmotion(next);

          resetTimerRef.current = setTimeout(() => {
            if (!isInteractingRef.current) {
              setCurrentEmotion('idle');
            }
          }, 1600);
        }
        cycleIdleEmotions();
      }, delay);
    };

    cycleIdleEmotions();

    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    };
  }, []);

  // Track cursor pointer relative to mascot center
  const handlePointerMove = useCallback((e: MouseEvent) => {
    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const dx = (e.clientX - centerX) / (window.innerWidth / 2);
    const dy = (e.clientY - centerY) / (window.innerHeight / 2);

    // Limit rotation angles for natural look
    const rotY = Math.max(-24, Math.min(24, dx * 28));
    const rotX = Math.max(-20, Math.min(20, -dy * 24));
    const transX = Math.max(-14, Math.min(14, dx * 16));
    const transY = Math.max(-10, Math.min(10, dy * 12));

    setTransformStyle(
      `perspective(650px) rotateX(${rotX.toFixed(1)}deg) rotateY(${rotY.toFixed(1)}deg) translate3d(${transX.toFixed(1)}px, ${transY.toFixed(1)}px, 0)`
    );

    setShadowOffset({
      x: -rotY * 0.8,
      y: 18 - rotX * 0.5
    });

    // React to close proximity
    const dist = Math.hypot(e.clientX - centerX, e.clientY - centerY);
    if (dist < 100 && !isPoked) {
      isInteractingRef.current = true;
      if (currentEmotion !== 'surprised' && currentEmotion !== 'love' && currentEmotion !== 'wink') {
        setCurrentEmotion('surprised');
      }
    } else if (dist < 220 && !isPoked) {
      isInteractingRef.current = true;
      if (currentEmotion === 'idle') {
        setCurrentEmotion('happy');
      }
    }
  }, [currentEmotion, isPoked]);

  // Attach global pointer listener so mascot tracks cursor across the whole modal
  useEffect(() => {
    window.addEventListener('mousemove', handlePointerMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', handlePointerMove);
    };
  }, [handlePointerMove]);

  // Click or poke mascot
  const handleMascotClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsPoked(true);
    isInteractingRef.current = true;

    const clickReactions: MascotEmotion[] = ['love', 'wink', 'smug', 'happy'];
    const chosen = clickReactions[Math.floor(Math.random() * clickReactions.length)];
    setCurrentEmotion(chosen);

    if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    resetTimerRef.current = setTimeout(() => {
      setIsPoked(false);
      isInteractingRef.current = false;
      setCurrentEmotion('happy');
    }, 1800);
  };

  const handleMouseEnterMascot = () => {
    isInteractingRef.current = true;
    if (!isPoked) {
      const hoverEmotions: MascotEmotion[] = ['wink', 'smug', 'happy'];
      setCurrentEmotion(hoverEmotions[Math.floor(Math.random() * hoverEmotions.length)]);
    }
  };

  const handleMouseLeaveMascot = () => {
    if (!isPoked) {
      isInteractingRef.current = false;
      setCurrentEmotion('happy');
    }
  };

  const expressionDef = MASCOT_EXPRESSIONS[currentEmotion] || happy;

  return (
    <div
      ref={containerRef}
      className={`interactive-limo-mascot-wrap ${className}`}
      onClick={handleMascotClick}
      onMouseEnter={handleMouseEnterMascot}
      onMouseLeave={handleMouseLeaveMascot}
      title="Hi! I'm Limo. Click me!"
    >
      {/* Dynamic ambient back-glow */}
      <div className="mascot-aura-glow" />

      {/* 3D tracking mascot body */}
      <div
        className={`mascot-avatar-mesh ${isPoked ? 'mascot-poked-pulse' : ''}`}
        style={{
          transform: transformStyle,
          transition: isPoked ? 'transform 0.15s cubic-bezier(0.18, 0.89, 0.32, 1.28)' : 'transform 0.12s ease-out',
          width: size,
          height: size,
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

      {/* Dynamic 3D depth ground shadow */}
      <div
        className="mascot-ground-shadow"
        style={{
          width: size * 0.75,
          height: 18,
          transform: `translate(${shadowOffset.x}px, ${shadowOffset.y}px)`,
        }}
      />

      <style>{`
        .interactive-limo-mascot-wrap {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          user-select: none;
          padding: 10px;
        }

        .mascot-aura-glow {
          position: absolute;
          width: 200px;
          height: 200px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(59, 130, 246, 0.28) 0%, rgba(99, 102, 241, 0.12) 50%, transparent 70%);
          filter: blur(28px);
          pointer-events: none;
          z-index: 1;
        }

        .mascot-avatar-mesh {
          position: relative;
          z-index: 2;
          display: flex;
          align-items: center;
          justify-content: center;
          transform-style: preserve-3d;
          will-change: transform;
        }

        .mascot-poked-pulse {
          animation: mascotPop 0.45s cubic-bezier(0.18, 0.89, 0.32, 1.28);
        }

        .mascot-ground-shadow {
          background: radial-gradient(ellipse at center, rgba(0, 0, 0, 0.45) 0%, rgba(0, 0, 0, 0.15) 55%, transparent 75%);
          border-radius: 50%;
          margin-top: 4px;
          pointer-events: none;
          z-index: 1;
          transition: transform 0.12s ease-out;
        }

        @keyframes mascotPop {
          0% { transform: scale(1); }
          40% { transform: scale(1.14) translateY(-8px); }
          100% { transform: scale(1); }
        }
      `}</style>
    </div>
  );
};
