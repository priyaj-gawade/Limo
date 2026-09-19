import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Play, Pause, Download } from 'lucide-react';

interface LimoAudioPlayerProps {
  src: string;
  onDownload?: () => void;
  className?: string;
}

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export const LimoAudioPlayer: React.FC<LimoAudioPlayerProps> = ({
  src,
  onDownload,
  className = '',
}) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isSeeking, setIsSeeking] = useState(false);

  // Synchronize audio element events
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => {
      if (!isSeeking) {
        setCurrentTime(audio.currentTime);
        if (audio.duration && audio.currentTime >= audio.duration) {
          setIsPlaying(false);
          setIsCompleted(true);
        }
      }
    };

    const onLoadedMetadata = () => {
      if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration)) {
        setDuration(audio.duration);
      }
    };

    const onDurationChange = () => {
      if (audio.duration && !isNaN(audio.duration) && isFinite(audio.duration)) {
        setDuration(audio.duration);
      }
    };

    const onEnded = () => {
      setIsPlaying(false);
      setIsCompleted(true);
      setCurrentTime(audio.duration || 0);
    };

    const onPlay = () => {
      setIsPlaying(true);
      setIsCompleted(false);
    };

    const onPause = () => {
      setIsPlaying(false);
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
    };
  }, [isSeeking]);

  // Handle single control button click
  // - Clicking while playing pauses
  // - Clicking while paused plays
  // - Clicking when completed replays from the beginning
  const handleTogglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isCompleted || (audio.duration && audio.currentTime >= audio.duration)) {
      // Replay from beginning
      audio.currentTime = 0;
      setCurrentTime(0);
      setIsCompleted(false);
      audio.play().catch(console.error);
    } else if (isPlaying) {
      audio.pause();
    } else {
      audio.play().catch(console.error);
    }
  };

  // Determine active icon:
  // When playing -> show Pause icon
  // When paused or completed -> show Play icon
  const showPauseIcon = isPlaying;

  // Handle scrubbing / seeking
  const seekToPosition = useCallback(
    (clientX: number) => {
      const audio = audioRef.current;
      const track = trackRef.current;
      if (!audio || !track || !duration) return;

      const rect = track.getBoundingClientRect();
      const clickX = Math.max(0, Math.min(clientX - rect.left, rect.width));
      const ratio = clickX / rect.width;
      const targetTime = ratio * duration;

      audio.currentTime = targetTime;
      setCurrentTime(targetTime);
      if (isCompleted) {
        setIsCompleted(false);
      }
    },
    [duration, isCompleted]
  );

  const handleTrackMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    setIsSeeking(true);
    seekToPosition(e.clientX);

    const onMouseMove = (moveEvent: MouseEvent) => {
      seekToPosition(moveEvent.clientX);
    };

    const onMouseUp = () => {
      setIsSeeking(false);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const progressPercent = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  return (
    <div className={`limo-step-audio-player ${className}`}>
      <audio ref={audioRef} src={src} preload="metadata" />

      {/* Progress Track Capsule */}
      <div
        className="audio-track-capsule"
        ref={trackRef}
        onMouseDown={handleTrackMouseDown}
        role="slider"
        aria-label="Audio progress scrubber"
        aria-valuenow={currentTime}
        aria-valuemax={duration}
        tabIndex={0}
      >
        <div className="audio-rail">
          <div
            className="audio-fill"
            style={{ width: `${progressPercent}%` }}
          >
            <span className="audio-fill-thumb" />
          </div>
        </div>
        <span className="audio-time-label">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>

      {/* Single Play/Pause Control Button */}
      <button
        type="button"
        className="audio-circle-btn audio-play-btn"
        onClick={handleTogglePlay}
        title={isCompleted ? 'Replay audio' : isPlaying ? 'Pause' : 'Play'}
        aria-label={isCompleted ? 'Replay audio' : isPlaying ? 'Pause' : 'Play'}
      >
        {showPauseIcon ? (
          <Pause size={17} className="audio-btn-icon" fill="currentColor" />
        ) : (
          <Play size={17} className="audio-btn-icon audio-play-triangle" fill="currentColor" />
        )}
      </button>

      {/* Matching Circular Download Button */}
      {onDownload && (
        <button
          type="button"
          className="audio-circle-btn audio-download-btn"
          onClick={onDownload}
          title="Download MP3"
          aria-label="Download MP3"
        >
          <Download size={17} className="audio-btn-icon" />
        </button>
      )}

      <style>{`
        .limo-step-audio-player {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          margin-top: 8px;
          margin-bottom: 4px;
          max-width: 100%;
        }

        .audio-track-capsule {
          height: 42px;
          min-width: 220px;
          max-width: 360px;
          flex: 1;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 0 16px;
          border-radius: 9999px;
          background: #262626;
          border: 1px solid rgba(255, 255, 255, 0.08);
          cursor: pointer;
          user-select: none;
          transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        }

        [data-theme="light"] .audio-track-capsule {
          background: #f4f4f7;
          border: 1px solid rgba(0, 0, 0, 0.07);
        }

        .audio-track-capsule:hover {
          background: #2a2a2a;
          border-color: rgba(255, 255, 255, 0.14);
        }

        [data-theme="light"] .audio-track-capsule:hover {
          background: #eaeaf0;
          border-color: rgba(0, 0, 0, 0.12);
        }

        .audio-rail {
          flex: 1;
          height: 4px;
          border-radius: 9999px;
          background: rgba(255, 255, 255, 0.15);
          position: relative;
          overflow: visible;
        }

        [data-theme="light"] .audio-rail {
          background: rgba(0, 0, 0, 0.12);
        }

        .audio-fill {
          height: 100%;
          border-radius: 9999px;
          background: #f0f0ef;
          position: relative;
          transition: width 0.06s linear;
        }

        [data-theme="light"] .audio-fill {
          background: #181817;
        }

        .audio-fill-thumb {
          position: absolute;
          right: -4px;
          top: 50%;
          transform: translateY(-50%);
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #ffffff;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
          opacity: 0;
          transition: opacity 0.15s ease, transform 0.15s ease;
        }

        [data-theme="light"] .audio-fill-thumb {
          background: #181817;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
        }

        .audio-track-capsule:hover .audio-fill-thumb {
          opacity: 1;
          transform: translateY(-50%) scale(1.2);
        }

        .audio-time-label {
          font-size: 11.5px;
          font-weight: 500;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          letter-spacing: -0.01em;
          color: rgba(255, 255, 255, 0.55);
          white-space: nowrap;
        }

        [data-theme="light"] .audio-time-label {
          color: rgba(0, 0, 0, 0.55);
        }

        .audio-circle-btn {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #262626;
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #f0f0ef;
          cursor: pointer;
          flex-shrink: 0;
          outline: none;
          transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.15s ease, border-color 0.15s ease;
        }

        [data-theme="light"] .audio-circle-btn {
          background: #f4f4f7;
          border: 1px solid rgba(0, 0, 0, 0.07);
          color: #181817;
        }

        .audio-circle-btn:hover {
          background: #303030;
          border-color: rgba(255, 255, 255, 0.16);
          transform: scale(1.05);
        }

        [data-theme="light"] .audio-circle-btn:hover {
          background: #eaeaf0;
          border-color: rgba(0, 0, 0, 0.14);
          transform: scale(1.05);
        }

        .audio-circle-btn:active {
          transform: scale(0.92);
        }

        .audio-btn-icon {
          display: block;
        }

        .audio-play-triangle {
          margin-left: 2px;
        }
      `}</style>
    </div>
  );
};
