import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Volume1,
  Maximize,
  Minimize,
  Download,
  RotateCcw,
} from 'lucide-react';
import { Artifact } from '../types';

interface VideoPlayerCardProps {
  artifact: Artifact;
  onDownloadArtifact?: (art: Artifact) => void;
}

type PlaybackMode = 'idle' | 'hover_preview' | 'active_playback';

export const VideoPlayerCard: React.FC<VideoPlayerCardProps> = ({
  artifact,
  onDownloadArtifact,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const progressBarRef = useRef<HTMLDivElement>(null);
  const hoverDebounceTimer = useRef<NodeJS.Timeout | null>(null);
  const controlsFadeTimer = useRef<NodeJS.Timeout | null>(null);

  // Player State
  const [playbackMode, setPlaybackMode] = useState<PlaybackMode>('idle');
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(() => {
    return Number(artifact.metadata?.duration_seconds) || 0;
  });
  const [bufferedEnd, setBufferedEnd] = useState<number>(0);
  const [volume, setVolume] = useState<number>(1);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [playbackRate, setPlaybackRate] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showControls, setShowControls] = useState<boolean>(true);
  const [isHoveringVol, setIsHoveringVol] = useState<boolean>(false);
  const [isSeeking, setIsSeeking] = useState<boolean>(false);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [hoverPos, setHoverPos] = useState<number>(0);
  const [posterLoaded, setPosterLoaded] = useState<boolean>(true);

  // Aspect ratio resolution
  const aspectRatio = artifact.metadata?.aspect_ratio || '16:9';
  const getAspectRatioPadding = () => {
    if (aspectRatio === '9:16') return '177.77%'; // 9:16 vertical
    if (aspectRatio === '1:1') return '100%'; // 1:1 square
    return '56.25%'; // 16:9 widescreen
  };

  const streamUrl = `/api/v1/artifacts/${artifact.id}/stream`;
  const posterUrl = artifact.thumbnailUrl || `/api/v1/artifacts/${artifact.id}/thumbnail`;
  const downloadUrl = `/api/v1/artifacts/${artifact.id}/download`;

  // Format time (MM:SS)
  const formatTime = (secs: number) => {
    if (isNaN(secs) || secs < 0) return '0:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  // Reset controls fade-out timer
  const scheduleControlsFade = useCallback(() => {
    setShowControls(true);
    if (controlsFadeTimer.current) clearTimeout(controlsFadeTimer.current);
    if (playbackMode === 'active_playback' && isPlaying) {
      controlsFadeTimer.current = setTimeout(() => {
        setShowControls(false);
      }, 2500);
    }
  }, [playbackMode, isPlaying]);

  // Fullscreen state synchronization
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isCurrentFullscreen = document.fullscreenElement === containerRef.current;
      setIsFullscreen(isCurrentFullscreen);
      if (isCurrentFullscreen) {
        scheduleControlsFade();
      }
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, [scheduleControlsFade]);

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only react if container is in fullscreen or hovered/focused
      const activeEl = document.activeElement;
      const isInput = activeEl?.tagName === 'INPUT' || activeEl?.tagName === 'TEXTAREA';
      if (isInput) return;

      if (e.key === 'f' || e.key === 'F') {
        if (isFullscreen || containerRef.current?.matches(':hover')) {
          e.preventDefault();
          toggleFullscreen();
        }
      } else if (e.key === ' ' || e.key === 'k' || e.key === 'K') {
        if (containerRef.current?.matches(':hover') || isFullscreen) {
          e.preventDefault();
          togglePlayPause();
        }
      } else if (e.key === 'm' || e.key === 'M') {
        if (containerRef.current?.matches(':hover') || isFullscreen) {
          e.preventDefault();
          toggleMute();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen, playbackMode, isPlaying]);

  // Mouse Enter: hover preview debounced start
  const handleMouseEnter = () => {
    scheduleControlsFade();
    if (playbackMode === 'active_playback') {
      return; // Do nothing to active playback
    }

    // Set 150ms debounce for muted preview
    hoverDebounceTimer.current = setTimeout(() => {
      if (videoRef.current) {
        videoRef.current.muted = true;
        setIsMuted(true);
        videoRef.current.play().then(() => {
          setPlaybackMode('hover_preview');
          setIsPlaying(true);
        }).catch(() => {
          // Autoplay policy prevented preview
        });
      }
    }, 150);
  };

  // Mouse Leave: reset hover preview; do NOT interrupt active playback
  const handleMouseLeave = () => {
    if (hoverDebounceTimer.current) {
      clearTimeout(hoverDebounceTimer.current);
      hoverDebounceTimer.current = null;
    }

    if (playbackMode === 'hover_preview') {
      if (videoRef.current) {
        videoRef.current.pause();
        videoRef.current.currentTime = 0;
      }
      setPlaybackMode('idle');
      setIsPlaying(false);
      setCurrentTime(0);
    } else if (playbackMode === 'active_playback') {
      // In active playback, leaving does NOT pause or reset
      if (isPlaying) {
        scheduleControlsFade();
      }
    }
  };

  // Enter active playback (unmuted) on explicit user action
  const startActivePlayback = () => {
    if (!videoRef.current) return;
    if (hoverDebounceTimer.current) {
      clearTimeout(hoverDebounceTimer.current);
      hoverDebounceTimer.current = null;
    }

    videoRef.current.muted = false;
    videoRef.current.volume = volume;
    setIsMuted(false);
    videoRef.current.play().then(() => {
      setPlaybackMode('active_playback');
      setIsPlaying(true);
      scheduleControlsFade();
    }).catch((err) => {
      console.warn('Playback error:', err);
    });
  };

  // Toggle Play/Pause in active mode
  const togglePlayPause = () => {
    if (!videoRef.current) return;
    if (playbackMode !== 'active_playback') {
      startActivePlayback();
      return;
    }

    if (videoRef.current.paused) {
      videoRef.current.play();
      setIsPlaying(true);
      scheduleControlsFade();
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
      setShowControls(true);
      if (controlsFadeTimer.current) clearTimeout(controlsFadeTimer.current);
    }
  };

  // Toggle Mute
  const toggleMute = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!videoRef.current) return;
    const nextMuted = !isMuted;
    videoRef.current.muted = nextMuted;
    setIsMuted(nextMuted);
    if (!nextMuted && volume === 0) {
      videoRef.current.volume = 0.5;
      setVolume(0.5);
    }
    scheduleControlsFade();
  };

  // Volume slider change
  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    if (videoRef.current) {
      videoRef.current.volume = val;
      videoRef.current.muted = val === 0;
      setIsMuted(val === 0);
    }
    scheduleControlsFade();
  };

  // Speed toggle cycle: 1x -> 1.25x -> 1.5x -> 2x -> 1x
  const handleCycleSpeed = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!videoRef.current) return;
    const speeds = [1, 1.25, 1.5, 2];
    const nextIdx = (speeds.indexOf(playbackRate) + 1) % speeds.length;
    const nextSpeed = speeds[nextIdx];
    videoRef.current.playbackRate = nextSpeed;
    setPlaybackRate(nextSpeed);
    scheduleControlsFade();
  };

  // Toggle Fullscreen on container
  const toggleFullscreen = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!containerRef.current) return;

    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch((err) => {
        console.warn('Error attempting fullscreen:', err);
      });
    } else {
      document.exitFullscreen().catch((err) => {
        console.warn('Error exiting fullscreen:', err);
      });
    }
    scheduleControlsFade();
  };

  // Video Time Update & Buffered progress
  const handleTimeUpdate = () => {
    if (!videoRef.current || isSeeking) return;
    setCurrentTime(videoRef.current.currentTime);
    if (videoRef.current.buffered.length > 0) {
      setBufferedEnd(videoRef.current.buffered.end(videoRef.current.buffered.length - 1));
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const dur = videoRef.current.duration;
      if (!isNaN(dur) && dur > 0) {
        setDuration(dur);
      }
    }
  };

  const handleVideoEnded = () => {
    setIsPlaying(false);
    setShowControls(true);
    if (playbackMode === 'hover_preview') {
      setPlaybackMode('idle');
      setCurrentTime(0);
    }
  };

  // Scrubber seeking calculations
  const calculateSeekTime = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressBarRef.current || duration <= 0) return 0;
    const rect = progressBarRef.current.getBoundingClientRect();
    const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    return pos * duration;
  };

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const newTime = calculateSeekTime(e);
    if (videoRef.current) {
      videoRef.current.currentTime = newTime;
      setCurrentTime(newTime);
    }
    if (playbackMode !== 'active_playback') {
      startActivePlayback();
    }
    scheduleControlsFade();
  };

  const handleProgressMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressBarRef.current || duration <= 0) return;
    const rect = progressBarRef.current.getBoundingClientRect();
    const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setHoverPos(e.clientX - rect.left);
    setHoverTime(pos * duration);
  };

  const handleProgressMouseLeave = () => {
    setHoverTime(null);
  };

  // Download Action
  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDownloadArtifact) {
      onDownloadArtifact(artifact);
    } else {
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${artifact.title.replace(/\s+/g, '_')}${artifact.fileFormat || '.mp4'}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;
  const bufferedPercent = duration > 0 ? (bufferedEnd / duration) * 100 : 0;

  return (
    <div className="limo-video-player-wrapper">
      <div
        ref={containerRef}
        className={`limo-video-container ${isFullscreen ? 'is-fullscreen' : ''} ${
          playbackMode === 'idle' ? 'mode-idle' : ''
        }`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onMouseMove={scheduleControlsFade}
        onClick={togglePlayPause}
      >
        {/* Aspect Ratio Box */}
        <div
          className="video-ratio-box"
          style={{ paddingTop: isFullscreen ? '0' : getAspectRatioPadding() }}
        >
          <video
            ref={videoRef}
            src={streamUrl}
            poster={posterUrl}
            preload="metadata"
            playsInline
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onEnded={handleVideoEnded}
            className="limo-native-video"
          />

          {/* Idle Poster Overlay with Limo-Branded Center Play Control */}
          {playbackMode === 'idle' && (
            <div className="video-idle-overlay">
              {posterLoaded && (
                <img
                  src={posterUrl}
                  alt={artifact.title}
                  className="video-poster-bg"
                  onError={() => setPosterLoaded(false)}
                />
              )}
              <button
                className="limo-center-play-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  startActivePlayback();
                }}
                title="Play video"
                aria-label="Play video"
              >
                <div className="limo-center-play-inner">
                  <Play size={24} className="limo-play-icon" />
                </div>
              </button>
            </div>
          )}

          {/* Floating Download Button - TOP-RIGHT in Normal View */}
          {!isFullscreen && (
            <button
              className="in-frame-download-btn normal-view-download"
              onClick={handleDownload}
              title="Download MP4"
            >
              <Download size={15} />
              <span className="btn-label">Download</span>
            </button>
          )}

          {/* In-Frame YouTube Control Bar */}
          <div
            className={`video-controls-overlay ${
              showControls || !isPlaying ? 'controls-visible' : 'controls-hidden'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Scrubber Progress Bar */}
            <div
              ref={progressBarRef}
              className="video-progress-bar-container"
              onClick={handleProgressClick}
              onMouseMove={handleProgressMouseMove}
              onMouseLeave={handleProgressMouseLeave}
            >
              {/* Hover Tooltip */}
              {hoverTime !== null && (
                <div
                  className="scrubber-hover-time"
                  style={{ left: `${hoverPos}px` }}
                >
                  {formatTime(hoverTime)}
                </div>
              )}
              <div className="progress-bar-rail">
                <div
                  className="progress-buffered-bar"
                  style={{ width: `${bufferedPercent}%` }}
                />
                <div
                  className="progress-played-bar"
                  style={{ width: `${progressPercent}%` }}
                />
                <div
                  className="progress-scrubber-thumb"
                  style={{ left: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* Controls Bottom Row */}
            <div className="video-controls-row">
              {/* Left Cluster: Play/Pause, Volume, Time, Title */}
              <div className="controls-cluster left-cluster">
                <button
                  className="control-icon-btn play-pause-btn"
                  onClick={togglePlayPause}
                  title={isPlaying ? 'Pause (k)' : 'Play (k)'}
                >
                  {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                </button>

                <div
                  className="volume-control-wrapper"
                  onMouseEnter={() => setIsHoveringVol(true)}
                  onMouseLeave={() => setIsHoveringVol(false)}
                >
                  <button
                    className="control-icon-btn"
                    onClick={toggleMute}
                    title={isMuted ? 'Unmute (m)' : 'Mute (m)'}
                  >
                    {isMuted || volume === 0 ? (
                      <VolumeX size={18} />
                    ) : volume < 0.5 ? (
                      <Volume1 size={18} />
                    ) : (
                      <Volume2 size={18} />
                    )}
                  </button>
                  <div
                    className={`volume-slider-box ${isHoveringVol ? 'slider-open' : ''}`}
                  >
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={isMuted ? 0 : volume}
                      onChange={handleVolumeChange}
                      className="volume-slider-range"
                      title="Volume"
                    />
                  </div>
                </div>

                <div className="video-time-display">
                  <span className="current-time">{formatTime(currentTime)}</span>
                  <span className="time-divider"> / </span>
                  <span className="total-duration">{formatTime(duration)}</span>
                </div>

                <div className="video-title-pill" title={artifact.title}>
                  <span className="badge-aspect">{aspectRatio}</span>
                  <span className="video-header-title">{artifact.title}</span>
                </div>
              </div>

              {/* Right Cluster: Speed, Download (Fullscreen only), Fullscreen / F Exit */}
              <div className="controls-cluster right-cluster">
                {/* Playback Rate / Speed Selector */}
                <button
                  className="control-text-btn speed-btn"
                  onClick={handleCycleSpeed}
                  title="Playback speed"
                >
                  {playbackRate}x
                </button>

                {/* FULLSCREEN MODE: Download is SECOND-TO-LAST on the bottom right */}
                {isFullscreen && (
                  <button
                    className="control-icon-btn fs-download-btn"
                    onClick={handleDownload}
                    title="Download MP4"
                  >
                    <Download size={18} />
                  </button>
                )}

                {/* Normal View: Maximize to Fullscreen. Fullscreen Mode: Compact 'F' final control */}
                {isFullscreen ? (
                  <button
                    className="control-text-btn fs-exit-f-btn"
                    onClick={toggleFullscreen}
                    title="Exit Fullscreen (F)"
                  >
                    <span className="f-label">F</span>
                  </button>
                ) : (
                  <button
                    className="control-icon-btn fullscreen-btn"
                    onClick={toggleFullscreen}
                    title="Fullscreen (f)"
                  >
                    <Maximize size={18} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        .limo-video-player-wrapper {
          width: 100%;
          max-width: 720px;
          margin-top: 10px;
        }

        .limo-video-container {
          position: relative;
          width: 100%;
          background: #000000;
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
          cursor: pointer;
          user-select: none;
        }

        .limo-video-container.is-fullscreen {
          border-radius: 0;
          border: none;
          width: 100vw;
          height: 100vh;
          max-width: 100vw;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .video-ratio-box {
          position: relative;
          width: 100%;
        }

        .limo-video-container.is-fullscreen .video-ratio-box {
          height: 100%;
          padding-top: 0 !important;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .limo-native-video {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          object-fit: contain;
          background: #000;
        }

        /* Idle Poster Overlay */
        .video-idle-overlay {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #000;
          z-index: 4;
        }

        .video-poster-bg {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          object-fit: contain;
        }

        /* Limo Center Play Control */
        .limo-center-play-btn {
          position: relative;
          z-index: 5;
          background: transparent;
          border: none;
          padding: 0;
          cursor: pointer;
          outline: none;
        }

        .limo-center-play-inner {
          width: 60px;
          height: 60px;
          background: rgba(20, 20, 19, 0.78);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.18);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.3);
          transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .limo-center-play-btn:hover .limo-center-play-inner {
          background: rgba(38, 38, 37, 0.94);
          border-color: rgba(255, 255, 255, 0.4);
          transform: scale(1.08);
          box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6), 0 0 16px rgba(255, 255, 255, 0.12);
        }

        .limo-center-play-btn:active .limo-center-play-inner {
          transform: scale(0.96);
        }

        .limo-play-icon {
          color: #f0f0ef;
          fill: #f0f0ef;
          margin-left: 3px;
          transition: transform 0.2s ease, color 0.2s ease;
        }

        .limo-center-play-btn:hover .limo-play-icon {
          color: #ffffff;
          fill: #ffffff;
          transform: scale(1.04);
        }

        /* In-Frame Download Button - Normal View */
        .in-frame-download-btn {
          position: absolute;
          top: 12px;
          right: 12px;
          z-index: 10;
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(24, 24, 23, 0.85);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.16);
          color: #f0f0ef;
          padding: 6px 12px;
          border-radius: 9999px;
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }

        .in-frame-download-btn:hover {
          background: rgba(255, 255, 255, 0.15);
          border-color: rgba(255, 255, 255, 0.3);
          transform: translateY(-1px);
        }

        /* Video Controls Overlay */
        .video-controls-overlay {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          z-index: 8;
          padding: 0 14px 10px 14px;
          background: linear-gradient(to top, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0.3) 60%, transparent 100%);
          transition: opacity 0.25s ease;
        }

        .controls-visible {
          opacity: 1;
          pointer-events: auto;
        }

        .controls-hidden {
          opacity: 0;
          pointer-events: none;
        }

        /* Scrubber Bar */
        .video-progress-bar-container {
          position: relative;
          width: 100%;
          height: 14px;
          display: flex;
          align-items: center;
          cursor: pointer;
        }

        .progress-bar-rail {
          position: relative;
          width: 100%;
          height: 3px;
          background: rgba(255, 255, 255, 0.25);
          border-radius: 2px;
          transition: height 0.1s ease;
        }

        .video-progress-bar-container:hover .progress-bar-rail {
          height: 5px;
        }

        .progress-buffered-bar {
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          background: rgba(255, 255, 255, 0.4);
          border-radius: 2px;
        }

        .progress-played-bar {
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          background: #ffffff;
          border-radius: 2px;
        }

        .progress-scrubber-thumb {
          position: absolute;
          top: 50%;
          width: 12px;
          height: 12px;
          background: #ffffff;
          border-radius: 50%;
          transform: translate(-50%, -50%) scale(0);
          transition: transform 0.1s ease;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.6);
        }

        .video-progress-bar-container:hover .progress-scrubber-thumb {
          transform: translate(-50%, -50%) scale(1);
        }

        .scrubber-hover-time {
          position: absolute;
          bottom: 20px;
          transform: translateX(-50%);
          background: rgba(20, 20, 19, 0.9);
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 11px;
          color: #fff;
          white-space: nowrap;
          pointer-events: none;
        }

        /* Controls Row */
        .video-controls-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-top: 4px;
        }

        .controls-cluster {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .control-icon-btn {
          background: transparent;
          border: none;
          color: #f0f0ef;
          cursor: pointer;
          padding: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 4px;
          transition: color 0.15s ease, transform 0.1s ease;
        }

        .control-icon-btn:hover {
          color: #ffffff;
          transform: scale(1.08);
        }

        .control-text-btn {
          background: rgba(255, 255, 255, 0.08);
          border: 1px solid rgba(255, 255, 255, 0.14);
          color: #f0f0ef;
          padding: 3px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .control-text-btn:hover {
          background: rgba(255, 255, 255, 0.18);
          color: #ffffff;
        }

        /* Fullscreen final control 'F' button */
        .fs-exit-f-btn {
          background: rgba(255, 255, 255, 0.12);
          border: 1px solid rgba(255, 255, 255, 0.22);
          color: #ffffff;
          width: 26px;
          height: 26px;
          padding: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 4px;
          font-size: 13px;
          font-weight: 700;
          transition: all 0.15s ease;
        }

        .fs-exit-f-btn:hover {
          background: rgba(255, 255, 255, 0.22);
          border-color: rgba(255, 255, 255, 0.4);
          transform: scale(1.05);
        }

        /* Volume Control */
        .volume-control-wrapper {
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .volume-slider-box {
          width: 0;
          opacity: 0;
          overflow: hidden;
          transition: width 0.2s ease, opacity 0.2s ease;
          display: flex;
          align-items: center;
        }

        .volume-slider-box.slider-open {
          width: 60px;
          opacity: 1;
        }

        .volume-slider-range {
          width: 60px;
          height: 3px;
          accent-color: #ffffff;
          cursor: pointer;
        }

        /* Time Display */
        .video-time-display {
          font-size: 12px;
          color: rgba(255, 255, 255, 0.8);
          font-variant-numeric: tabular-nums;
          white-space: nowrap;
        }

        .time-divider {
          color: rgba(255, 255, 255, 0.4);
          margin: 0 2px;
        }

        /* Title Pill */
        .video-title-pill {
          display: flex;
          align-items: center;
          gap: 6px;
          background: rgba(255, 255, 255, 0.06);
          padding: 2px 8px;
          border-radius: 4px;
          max-width: 220px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .badge-aspect {
          font-size: 10px;
          font-weight: 600;
          color: #60a5fa;
          background: rgba(96, 165, 250, 0.15);
          padding: 1px 4px;
          border-radius: 3px;
        }

        .video-header-title {
          font-size: 11.5px;
          color: rgba(255, 255, 255, 0.7);
          overflow: hidden;
          text-overflow: ellipsis;
        }
      `}</style>
    </div>
  );
};
