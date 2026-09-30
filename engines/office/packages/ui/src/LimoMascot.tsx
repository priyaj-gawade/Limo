import React, { useState, useEffect, useRef } from 'react'
import { Blobatar } from '@blobatar/react'
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
  sleepy,
} from 'blobatar/expression'
import 'blobatar/motion.css'

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
}

export type MascotEmotion = keyof typeof EXPRESSION_MAP

export interface LimoMascotProps {
  size?: number
  isGenerating?: boolean
  emotion?: MascotEmotion
  interactive?: boolean
  className?: string
  title?: string
}

export const LimoMascot: React.FC<LimoMascotProps> = ({
  size = 26,
  isGenerating = false,
  emotion,
  interactive = true,
  className = '',
  title = 'Limo',
}) => {
  const [currentEmotion, setCurrentEmotion] = useState<MascotEmotion>(() => {
    if (isGenerating) return 'thinking'
    return emotion || 'happy'
  })

  const gestureTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Synchronize when isGenerating or emotion prop changes
  useEffect(() => {
    if (isGenerating) {
      setCurrentEmotion('thinking')
      const thinkingCycle: MascotEmotion[] = ['thinking', 'thinking', 'surprised', 'thinking', 'smug']
      let step = 0

      const interval = setInterval(() => {
        step = (step + 1) % thinkingCycle.length
        const nextEmotion = thinkingCycle[step] ?? 'thinking'
        setCurrentEmotion(nextEmotion)
      }, 3200)

      return () => clearInterval(interval)
    } else {
      setCurrentEmotion(emotion || 'happy')

      // Autonomous idle life: occasionally wink, smug or smile
      const scheduleIdleGesture = () => {
        const nextDelay = 12000 + Math.random() * 8000
        gestureTimerRef.current = setTimeout(() => {
          const idleGestures: MascotEmotion[] = ['wink', 'smug', 'happy', 'surprised']
          const picked = idleGestures[Math.floor(Math.random() * idleGestures.length)] ?? 'wink'
          setCurrentEmotion(picked)

          gestureTimerRef.current = setTimeout(() => {
            setCurrentEmotion(emotion || 'happy')
            scheduleIdleGesture()
          }, 1800)
        }, nextDelay)
      }

      scheduleIdleGesture()

      return () => {
        if (gestureTimerRef.current) clearTimeout(gestureTimerRef.current)
      }
    }
  }, [isGenerating, emotion])

  // Playful interaction on click
  const handleClick = (e: React.MouseEvent) => {
    if (!interactive) return
    e.stopPropagation()
    const reactions: MascotEmotion[] = ['wink', 'surprised', 'love', 'smug', 'happy']
    const nextReaction = reactions[Math.floor(Math.random() * reactions.length)] ?? 'happy'
    setCurrentEmotion(nextReaction)

    if (gestureTimerRef.current) clearTimeout(gestureTimerRef.current)
    gestureTimerRef.current = setTimeout(() => {
      setCurrentEmotion(isGenerating ? 'thinking' : emotion || 'happy')
    }, 2000)
  }

  const handleMouseEnter = () => {
    if (!interactive || isGenerating) return
    const hoverReactions: MascotEmotion[] = ['wink', 'smug', 'happy']
    const next = hoverReactions[Math.floor(Math.random() * hoverReactions.length)] ?? 'happy'
    setCurrentEmotion(next)
  }

  const handleMouseLeave = () => {
    if (!interactive || isGenerating) return
    setCurrentEmotion(emotion || 'happy')
  }

  const resolvedExpression = EXPRESSION_MAP[currentEmotion] || happy

  return (
    <div
      className={`limo-mascot-container ${className} ${isGenerating ? 'is-thinking' : ''}`}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      title={title}
      style={{
        width: size,
        height: size,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: interactive ? 'pointer' : 'default',
        flexShrink: 0,
        userSelect: 'none',
        lineHeight: 0,
      }}
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
  )
}

export default LimoMascot
