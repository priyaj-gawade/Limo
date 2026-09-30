import { Artifact } from '../types';

export interface SocialSlideItem {
  slide_number: number;
  type?: string;
  headline: string;
  subheadline?: string;
  body?: string;
  visual_prompt?: string;
}

export interface TweetItem {
  tweet_number: number;
  text: string;
  char_count: number;
}

export interface ParsedSocialDraft {
  isDraft: boolean;
  platform: 'linkedin' | 'twitter' | 'instagram' | string;
  format: string;
  hook?: string;
  content: string;
  hashtags?: string[];
  source_references?: string[];
  warnings?: string[];
  media_suggestion?: string;
  status: string;
  tweets?: TweetItem[];
  slides?: SocialSlideItem[];
  cleanContent: string;
  artifact?: Artifact;
}

/**
 * Validates whether an object is a minimally valid social draft payload.
 */
function isValidSocialPayload(obj: any): boolean {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return false;
  const platform = String(obj.platform || '').toLowerCase().trim();
  if (!['linkedin', 'twitter', 'x', 'instagram'].includes(platform)) return false;

  const hasFormat = typeof obj.format === 'string' && obj.format.trim().length > 0;
  const hasContent = typeof obj.content === 'string' && obj.content.trim().length > 0;
  const hasItems = Array.isArray(obj.items) && obj.items.length > 0;
  const hasSlides = Array.isArray(obj.slides) && obj.slides.length > 0;
  const hasTweets = Array.isArray(obj.tweets) && obj.tweets.length > 0;

  return hasFormat && (hasContent || hasItems || hasSlides || hasTweets);
}

/**
 * Attempts to extract a valid JSON social draft payload and its optional conversational preamble.
 */
function extractValidSocialJson(text: string): { data: any; preamble: string } | null {
  if (!text || typeof text !== 'string') return null;

  try {
    const raw = text.trim();
    let preamble = '';

    const fenceMatch = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/i);
    if (fenceMatch) {
      const parsed = JSON.parse(fenceMatch[1].trim());
      const idx = text.indexOf(fenceMatch[0]);
      if (idx > 0) {
        preamble = text.substring(0, idx).trim();
      }
      if (isValidSocialPayload(parsed)) {
        return { data: parsed, preamble };
      }
    }

    if (raw.startsWith('{') && raw.endsWith('}')) {
      const parsed = JSON.parse(raw);
      if (isValidSocialPayload(parsed)) {
        return { data: parsed, preamble: '' };
      }
    }

    const firstBrace = text.indexOf('{');
    const lastBrace = text.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace > firstBrace) {
      const candidate = text.substring(firstBrace, lastBrace + 1).trim();
      const parsed = JSON.parse(candidate);
      if (firstBrace > 0) {
        preamble = text.substring(0, firstBrace).trim();
      }
      if (isValidSocialPayload(parsed)) {
        return { data: parsed, preamble };
      }
    }
  } catch {
    // Not valid JSON
  }

  return null;
}

/**
 * Strips raw YAML/JSON structured social metadata keys from visible chat text.
 * Ensures internal keys and schema structures are never visible as text.
 */
export function stripSocialMetadata(text: string): string {
  if (!text) return '';

  // Remove code blocks wrapping social draft yaml or json if any
  let cleaned = text.replace(/```(?:ya?ml|json)?\s*(platform:[\s\S]*?)```/gi, '');
  cleaned = cleaned.replace(/```(?:json)?\s*(\{\s*["']platform["'][\s\S]*?\})\s*```/gi, '');

  // If text is or contains a bare JSON social draft, strip the JSON object
  const firstBrace = cleaned.indexOf('{');
  const lastBrace = cleaned.lastIndexOf('}');
  if (firstBrace !== -1 && lastBrace > firstBrace) {
    const candidate = cleaned.substring(firstBrace, lastBrace + 1);
    try {
      const parsed = JSON.parse(candidate);
      if (isValidSocialPayload(parsed)) {
        cleaned = (cleaned.substring(0, firstBrace) + cleaned.substring(lastBrace + 1)).trim();
      }
    } catch {
      // Not valid JSON
    }
  }

  // Remove individual YAML header lines
  const lines = cleaned.split('\n');
  const filteredLines: string[] = [];
  let inMetadataBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Check if line is a metadata header key
    const isMetaKey = /^(?:-\s*)?(?:platform|format|hook|hashtags|source_references|warnings|media_suggestion|status|total_tweets|total_slides):\s*/i.test(trimmed);
    const isContentKey = /^(?:-\s*)?content:\s*/i.test(trimmed);

    if (isMetaKey) {
      inMetadataBlock = true;
      continue;
    }

    if (isContentKey) {
      inMetadataBlock = false;
      const rest = line.replace(/^(?:-\s*)?content:\s*/i, '').trim();
      if (rest) {
        filteredLines.push(rest);
      }
      continue;
    }

    // Skip YAML list continuation items under hashtags/warnings/references if inside metadata block
    if (inMetadataBlock && (trimmed.startsWith('- ') || trimmed.startsWith('[') || trimmed.endsWith(']'))) {
      continue;
    }

    // If we were in metadata block and hit an empty line or normal text, reset
    if (inMetadataBlock && trimmed === '') {
      continue;
    }

    inMetadataBlock = false;
    filteredLines.push(line);
  }

  return filteredLines.join('\n').trim();
}

/**
 * Determines whether text contains a structured social media draft payload.
 */
export function isSocialDraftContent(text: string): boolean {
  if (!text || typeof text !== 'string') return false;

  // 1. Check JSON detection
  if (extractValidSocialJson(text) !== null) {
    return true;
  }

  // 2. Existing YAML fallback detection
  const hasPlatform = /(?:^|\n)\s*(?:-\s*)?platform:\s*["']?(linkedin|twitter|x|instagram)["']?/i.test(text);
  const hasSocialKeys = /(?:^|\n)\s*(?:-\s*)?(?:format|hook|hashtags|source_references|warnings|media_suggestion|status|content):\s*/i.test(text);

  return hasPlatform && hasSocialKeys;
}

/**
 * Frontend fallback parser for legacy chat history or rendering when an artifact is not present.
 * Extracts fields into a temporary in-memory render model for SocialDraftCard.
 * (Canonical parsing and artifact persistence belongs to the backend).
 */
export function parseSocialDraft(text: string): ParsedSocialDraft {
  if (!isSocialDraftContent(text)) {
    return {
      isDraft: false,
      platform: '',
      format: '',
      content: text,
      status: '',
      cleanContent: text,
    };
  }

  // 1. Try JSON extraction for legacy fallback
  const jsonExtract = extractValidSocialJson(text);
  if (jsonExtract) {
    const rawObj = jsonExtract.data;
    const preamble = jsonExtract.preamble;

    let platform = String(rawObj.platform || 'linkedin').toLowerCase().trim();
    if (platform === 'x') platform = 'twitter';

    const format = String(rawObj.format || (platform === 'twitter' ? 'thread' : 'post')).toLowerCase().trim();
    const hook = rawObj.hook ? String(rawObj.hook).trim() : undefined;
    const status = String(rawObj.status || 'Draft').trim();
    const media_suggestion = rawObj.media_suggestion ? String(rawObj.media_suggestion).trim() : undefined;

    // Hashtags
    let hashtags: string[] = [];
    if (Array.isArray(rawObj.hashtags)) {
      hashtags = rawObj.hashtags.map((h: any) => String(h).trim()).filter(Boolean);
    } else if (typeof rawObj.hashtags === 'string') {
      hashtags = rawObj.hashtags.split(/[\s,]+/).filter((h: string) => h.startsWith('#'));
    }

    // Source references
    let source_references: string[] = [];
    if (Array.isArray(rawObj.source_references)) {
      source_references = rawObj.source_references.map((r: any) => String(r).trim()).filter(Boolean);
    } else if (typeof rawObj.source_references === 'string') {
      source_references = [rawObj.source_references.trim()];
    }

    // Warnings
    let warnings: string[] = [];
    if (Array.isArray(rawObj.warnings)) {
      warnings = rawObj.warnings.map((w: any) => String(w).trim()).filter(Boolean);
    }

    // Content
    let content = typeof rawObj.content === 'string' ? rawObj.content.trim() : '';

    // Tweets
    let tweets: TweetItem[] = [];
    if (platform === 'twitter') {
      if (Array.isArray(rawObj.items) && rawObj.items.length > 0) {
        tweets = rawObj.items.map((item: any, idx: number) => {
          const txt = typeof item === 'object' ? String(item.text || item.content || '') : String(item);
          const num = typeof item === 'object' && item.tweet_number ? Number(item.tweet_number) : idx + 1;
          return { tweet_number: num, text: txt, char_count: txt.length };
        }).filter((t: TweetItem) => t.text.length > 0);
      } else if (Array.isArray(rawObj.tweets) && rawObj.tweets.length > 0) {
        tweets = rawObj.tweets.map((t: any, idx: number) => {
          const txt = String(t).trim();
          return { tweet_number: idx + 1, text: txt, char_count: txt.length };
        }).filter((t: TweetItem) => t.text.length > 0);
      } else if (content) {
        const threadParts = content.split(/(?:\n\s*---\s*\n|\n\s*---\s*$)/).map((p: string) => p.trim()).filter(Boolean);
        if (threadParts.length > 1) {
          tweets = threadParts.map((t: string, i: number) => ({ tweet_number: i + 1, text: t, char_count: t.length }));
        } else {
          tweets = [{ tweet_number: 1, text: content, char_count: content.length }];
        }
      }
    }

    // Slides
    let slides: SocialSlideItem[] = [];
    if (platform === 'instagram' || format === 'carousel') {
      const candidateSlides = Array.isArray(rawObj.slides)
        ? rawObj.slides
        : (Array.isArray(rawObj.items) && rawObj.items.length > 0 && typeof rawObj.items[0] === 'object' && (rawObj.items[0].headline || rawObj.items[0].slide_number) ? rawObj.items : null);

      if (candidateSlides) {
        slides = candidateSlides.map((s: any, idx: number) => ({
          slide_number: Number(s.slide_number || idx + 1),
          type: String(s.type || (idx === 0 ? 'cover' : 'insight')),
          headline: String(s.headline || `Slide ${idx + 1}`),
          subheadline: s.subheadline ? String(s.subheadline) : undefined,
          body: s.body ? String(s.body) : undefined,
          visual_prompt: (s.visual_prompt || s.visual) ? String(s.visual_prompt || s.visual) : undefined,
        }));
      }
    }

    // Platform Title & stats
    const platformTitle = platform === 'linkedin' ? 'LinkedIn' : (platform === 'twitter' ? 'X / Twitter' : 'Instagram');
    let stats = `${platformTitle} Post • Draft`;
    if (platform === 'twitter' && tweets.length > 0) {
      stats = `${tweets.length} Tweet${tweets.length > 1 ? 's' : ''} • Thread • Draft`;
    } else if (platform === 'instagram' && slides.length > 0) {
      stats = `${slides.length} Slides • Carousel • Draft`;
    }

    // Construct temporary in-memory render model for SocialDraftCard (Legacy/Fallback only)
    const artifactId = `render_draft_${platform}_${Date.now()}`;
    const artifact: Artifact = {
      id: artifactId,
      title: `${platformTitle} ${format === 'carousel' ? 'Carousel' : (format === 'thread' ? 'Thread' : 'Post')} Draft`,
      type: 'post',
      fileFormat: platform === 'twitter' ? '.json' : '.md',
      mimeType: platform === 'twitter' ? 'application/json' : 'text/markdown',
      skill: platform,
      stats,
      description: hook || `${platformTitle} draft deliverable`,
      previewContent: content,
      createdAt: new Date().toISOString(),
      metadata: {
        platform,
        format,
        hook,
        hashtags,
        source_references,
        warnings,
        media_suggestion,
        status,
        social_draft: {
          platform,
          format,
          hook,
          content,
          hashtags,
          source_references,
          warnings,
          media_suggestion,
          status,
          items: tweets.length > 0 ? tweets : (slides.length > 0 ? slides : undefined),
          tweets: tweets.length > 0 ? tweets.map((t) => t.text) : undefined,
          slides: slides.length > 0 ? slides : undefined,
          total_slides: slides.length > 0 ? slides.length : undefined,
        },
      },
    };

    return {
      isDraft: true,
      platform,
      format,
      hook,
      content,
      hashtags,
      source_references,
      warnings,
      media_suggestion,
      status,
      tweets: tweets.length > 0 ? tweets : undefined,
      slides: slides.length > 0 ? slides : undefined,
      cleanContent: preamble,
      artifact,
    };
  }

  // 2. Existing YAML parser fallback
  // Normalize code fences if wrapped
  let raw = text;
  const fenceMatch = raw.match(/```(?:ya?ml|json)?\s*([\s\S]*?)```/i);
  if (fenceMatch && /platform:\s*(linkedin|twitter|x|instagram)/i.test(fenceMatch[1])) {
    raw = fenceMatch[1];
  }

  // Extract preamble/intro before the metadata block (e.g. "Here's your draft:")
  let preamble = '';
  const platformIndex = raw.search(/(?:^|\n)\s*(?:-\s*)?platform:\s*/i);
  if (platformIndex > 0) {
    preamble = raw.substring(0, platformIndex).trim();
  }

  // Extract platform
  const platMatch = raw.match(/(?:^|\n)\s*(?:-\s*)?platform:\s*["']?([a-zA-Z0-9_-]+)["']?/i);
  let platform = (platMatch ? platMatch[1] : 'linkedin').toLowerCase();
  if (platform === 'x') platform = 'twitter';

  const extractScalarField = (key: string): string | undefined => {
    const match = raw.match(new RegExp(`(?:^|\\n)\\s*(?:-\\s*)?${key}:\\s*(?:["']([^\n]*)["']|([^\n]+))`, 'i'));
    if (match) {
      const val = (match[1] !== undefined ? match[1] : match[2]).trim();
      return val.replace(/^["']|["']$/g, '').trim();
    }
    return undefined;
  };

  // Extract format
  const format = (extractScalarField('format') || (platform === 'twitter' ? 'thread' : 'post')).toLowerCase();

  // Extract hook
  const hook = extractScalarField('hook');

  // Extract status
  const status = extractScalarField('status') || 'Draft';

  // Extract media_suggestion
  const media_suggestion = extractScalarField('media_suggestion');

  // Extract hashtags
  let hashtags: string[] = [];
  const hashMatch = raw.match(/(?:^|\n)\s*(?:-\s*)?hashtags:\s*(\[[^\]]*\]|[^\n]+)/i);
  if (hashMatch) {
    const rawHashes = hashMatch[1].trim();
    if (rawHashes.startsWith('[') && rawHashes.endsWith(']')) {
      try {
        hashtags = JSON.parse(rawHashes.replace(/'/g, '"'));
      } catch {
        hashtags = rawHashes.replace(/[\[\]"']/g, '').split(',').map((h) => h.trim()).filter(Boolean);
      }
    } else {
      hashtags = rawHashes.split(/[\s,]+/).filter((h) => h.startsWith('#'));
    }
  }

  // Extract source_references
  let source_references: string[] = [];
  const refMatch = raw.match(/(?:^|\n)\s*(?:-\s*)?source_references:\s*(\[[^\]]*\]|[^\n]+)/i);
  if (refMatch) {
    const rawRefs = refMatch[1].trim();
    if (rawRefs.startsWith('[') && rawRefs.endsWith(']')) {
      try {
        source_references = JSON.parse(rawRefs.replace(/'/g, '"'));
      } catch {
        source_references = rawRefs.replace(/[\[\]"']/g, '').split(',').map((r) => r.trim()).filter(Boolean);
      }
    } else {
      source_references = [rawRefs];
    }
  }

  // Extract warnings
  let warnings: string[] = [];
  const warnMatch = raw.match(/(?:^|\n)\s*(?:-\s*)?warnings:\s*(\[[^\]]*\]|[^\n]+)/i);
  if (warnMatch) {
    const rawWarn = warnMatch[1].trim();
    if (rawWarn.startsWith('[') && rawWarn.endsWith(']')) {
      try {
        warnings = JSON.parse(rawWarn.replace(/'/g, '"'));
      } catch {
        warnings = [];
      }
    }
  }

  // Extract content body
  let content = '';
  const contentMatch = raw.match(/(?:^|\n)\s*(?:-\s*)?content:\s*([\s\S]*)$/i);
  if (contentMatch) {
    content = contentMatch[1].trim();
  } else {
    // If no explicit content: tag, strip metadata lines and use remaining text
    content = stripSocialMetadata(raw);
  }

  // Handle Twitter thread extraction
  let tweets: TweetItem[] = [];
  if (platform === 'twitter') {
    // Check if content has thread breaks
    const threadDelimiterRegex = /(?:\n\s*---\s*\n|\n\s*---\s*$)/;
    const tweetNumberRegex = /(?:^|\n)(?:🧵\s*)?(\d+)\s*\/\s*(?:\d+|\{total\}|\{num\}|N)?[:\s-]/i;

    if (threadDelimiterRegex.test(content)) {
      const parts = content.split(threadDelimiterRegex).map((p) => p.trim()).filter(Boolean);
      tweets = parts.map((t, i) => ({
        tweet_number: i + 1,
        text: t,
        char_count: t.length,
      }));
    } else if (tweetNumberRegex.test(content)) {
      // Split on numbered tweets like 1/N, 2/N or 1:, 2:
      const lines = content.split('\n');
      const tweetBlocks: string[] = [];
      let currentBlock: string[] = [];

      for (const line of lines) {
        if (tweetNumberRegex.test(line) && currentBlock.length > 0) {
          tweetBlocks.push(currentBlock.join('\n').trim());
          currentBlock = [line];
        } else {
          currentBlock.push(line);
        }
      }
      if (currentBlock.length > 0) {
        tweetBlocks.push(currentBlock.join('\n').trim());
      }

      tweets = tweetBlocks.filter(Boolean).map((t, i) => ({
        tweet_number: i + 1,
        text: t,
        char_count: t.length,
      }));
    }

    if (tweets.length === 0 && content) {
      tweets = [{
        tweet_number: 1,
        text: content,
        char_count: content.length,
      }];
    }
  }

  // Handle Instagram carousel slide extraction
  let slides: SocialSlideItem[] = [];
  if (platform === 'instagram' || format === 'carousel') {
    const slideSplitRegex = /(?:^|\n)(?:###?\s*)?Slide\s*(\d+)[:\s-]*([^\n]*)/i;

    if (slideSplitRegex.test(content)) {
      // The caption is often before "Carousel Slides Breakdown:" or before "Slide 1"
      const breakdownIndex = content.search(/(?:Carousel\s+Slides\s+Breakdown|Slide\s*1[:\s-])/i);
      let captionText = content;
      let slidesSection = content;

      if (breakdownIndex > 0) {
        captionText = content.substring(0, breakdownIndex).trim();
        slidesSection = content.substring(breakdownIndex);
      }

      // Parse individual slides from slidesSection
      const slideMatches = Array.from(slidesSection.matchAll(/(?:^|\n)(?:###?\s*)?Slide\s*(\d+)[:\s-]*([^\n]*)([\s\S]*?)(?=(?:(?:^|\n)(?:###?\s*)?Slide\s*\d+)|\s*$)/gi));

      for (const sm of slideMatches) {
        const slideNum = parseInt(sm[1], 10);
        const slideHeader = sm[2].trim();
        const slideBody = sm[3].trim();

        // Parse Headline
        const hMatch = slideBody.match(/(?:•\s*)?Headline:\s*([^\n]+)/i);
        const headline = hMatch ? hMatch[1].trim() : (slideHeader || `Slide ${slideNum}`);

        // Parse Subheadline
        const subMatch = slideBody.match(/(?:•\s*)?Subheadline:\s*([^\n]+)/i);
        const subheadline = subMatch ? subMatch[1].trim() : undefined;

        // Parse Body text
        const bMatch = slideBody.match(/(?:•\s*)?Body:\s*([\s\S]*?)(?=(?:•\s*Visual|\n\s*•|\n\s*Slide|$))/i);
        const bodyText = bMatch ? bMatch[1].trim() : undefined;

        // Parse Visual cue
        const vMatch = slideBody.match(/(?:•\s*)?Visual(?:\s*Prompt)?:\s*([^\n]+)/i);
        const visual_prompt = vMatch ? vMatch[1].trim() : undefined;

        // Determine slide kind
        let type = 'insight';
        const lowerHeader = (slideHeader + ' ' + headline).toLowerCase();
        if (lowerHeader.includes('cover') || slideNum === 1) type = 'cover';
        else if (lowerHeader.includes('cta') || lowerHeader.includes('save') || lowerHeader.includes('follow')) type = 'cta';
        else if (lowerHeader.includes('data') || lowerHeader.includes('number')) type = 'data';

        slides.push({
          slide_number: slideNum,
          type,
          headline,
          subheadline,
          body: bodyText,
          visual_prompt,
        });
      }

      // Update content to clean caption if separated
      if (captionText) {
        content = captionText;
      }
    }
  }

  // Clean content of any remaining raw metadata keywords
  content = stripSocialMetadata(content);

  // Platform Title
  const platformTitle = platform === 'linkedin' ? 'LinkedIn' : (platform === 'twitter' ? 'X / Twitter' : 'Instagram');

  // Stats description
  let stats = `${platformTitle} Post • Draft`;
  if (platform === 'twitter' && tweets.length > 0) {
    stats = `${tweets.length} Tweet${tweets.length > 1 ? 's' : ''} • Thread • Draft`;
  } else if (platform === 'instagram' && slides.length > 0) {
    stats = `${slides.length} Slides • Carousel • Draft`;
  }

  // Construct first-class synthetic Artifact
  const artifactId = `art_draft_${platform}_${Date.now()}`;
  const artifact: Artifact = {
    id: artifactId,
    title: `${platformTitle} ${format === 'carousel' ? 'Carousel' : (format === 'thread' ? 'Thread' : 'Post')} Draft`,
    type: 'post',
    fileFormat: platform === 'twitter' ? '.json' : '.md',
    mimeType: platform === 'twitter' ? 'application/json' : 'text/markdown',
    skill: platform,
    stats,
    description: hook || `${platformTitle} draft deliverable`,
    previewContent: content,
    createdAt: new Date().toISOString(),
    metadata: {
      platform,
      format,
      hook,
      hashtags,
      source_references,
      warnings,
      media_suggestion,
      status: 'Draft',
      social_draft: {
        platform,
        format,
        hook,
        content,
        hashtags,
        source_references,
        warnings,
        media_suggestion,
        status: 'Draft',
        items: tweets.length > 0 ? tweets : undefined,
        tweets: tweets.length > 0 ? tweets.map((t) => t.text) : undefined,
        slides: slides.length > 0 ? slides : undefined,
        total_slides: slides.length > 0 ? slides.length : undefined,
      },
    },
  };

  return {
    isDraft: true,
    platform,
    format,
    hook,
    content,
    hashtags,
    source_references,
    warnings,
    media_suggestion,
    status,
    tweets: tweets.length > 0 ? tweets : undefined,
    slides: slides.length > 0 ? slides : undefined,
    cleanContent: preamble, // Only non-metadata preamble, or empty string
    artifact,
  };
}

/**
 * Converts formatted markdown text into clean, publishable plain text for clipboard copying.
 * Strips markdown symbols (**, ##, *, _, ~~) while preserving social hashtags (#Tag), bullets, and paragraphs.
 */
export function toPublishablePlainText(text: string): string {
  if (!text || typeof text !== 'string') return '';

  // 1. Strip any raw internal metadata keys if present
  let cleaned = stripSocialMetadata(text);

  // 2. Remove code blocks and inline code ticks
  cleaned = cleaned.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, '$1');
  cleaned = cleaned.replace(/`([^`]+)`/g, '$1');

  // 3. Remove bold and italic markers (**bold** -> bold, *italic* -> italic)
  cleaned = cleaned.replace(/\*\*([^*]+)\*\*/g, '$1');
  cleaned = cleaned.replace(/__([^_]+)__/g, '$1');
  cleaned = cleaned.replace(/(^|[^\w*])\*([^*\n]+)\*([^\w*]|$)/g, '$1$2$3');
  cleaned = cleaned.replace(/(^|[^\w_])_([^_\n]+)_([^\w_]|$)/g, '$1$2$3');
  cleaned = cleaned.replace(/~~([^~]+)~~/g, '$1');

  // 4. Remove Markdown heading indicators (# Heading -> Heading), while strictly preserving hashtags like #Micron
  cleaned = cleaned.replace(/^[ \t]*#{1,6}[ \t]+([^\n]+)$/gm, '$1');

  // 5. Convert Markdown links [Text](url) -> Text (url) or just Text if identical
  cleaned = cleaned.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, url) => {
    if (label.trim().toLowerCase() === url.trim().toLowerCase()) {
      return label;
    }
    return `${label} (${url})`;
  });

  // 6. Normalize list bullets (- item / * item -> • item)
  cleaned = cleaned.replace(/^[ \t]*[-*][ \t]+([^\n]+)$/gm, '• $1');

  // 7. Remove blockquote markers (> quote -> quote)
  cleaned = cleaned.replace(/^[ \t]*>[ \t]?/gm, '');

  // 8. Remove horizontal rules (---, ***, ___)
  cleaned = cleaned.replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, '');

  // 9. Normalize excessive blank lines (max 2 consecutive newlines)
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');

  return cleaned.trim();
}

