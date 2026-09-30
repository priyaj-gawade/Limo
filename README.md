<div align="center">

<img src="docs/media/limo-logo.png" alt="Limo Logo" width="100" height="100" />

# Limo

**An AI workspace that turns your content into useful work.**

Transform text, reports, documents, spreadsheets, images, audio, video, and web articles into production-ready documents, presentations, videos, and social media drafts.

</div>

---

<div align="center">


<video src=["docs/media/limo-github.mp4"](https://github.com/user-attachments/assets/48a922e4-76e3-4a26-8a59-f47e50df9ab4) controls="controls" width="100%" poster="docs/media/demo-poster.png"></video>

<sub>If the video does not play directly in your browser, you can <a href="docs/media/limo-github.mp4">download or watch the demo video directly</a>.</sub>

</div>

---

## What is Limo?

Organizations and professionals work with information spread across different formats: threat intelligence, policy papers, incident reports, spreadsheets, research documents, news articles, and raw media. Converting this raw information into finished deliverables usually requires manual synthesis, multiple tools, and specialized design effort.

**Limo** is an intelligent desktop workspace designed to automate this entire process. You provide source material in any supported format, select the outputs you need, and Limo analyzes the material, understands the context, and generates verified deliverables.

Everything you create remains organized as tangible files that you can preview, open, edit, and export.

---

## Key Capabilities

### Content Ingestion
Understand and extract information from multiple input formats in a single request:
- **Documents & Text**: Word documents (`.docx`), Adobe PDF files, plain text, and markdown
- **Spreadsheets**: Excel workbooks (`.xlsx`) with structured tables and formulas
- **Media**: Static images, audio recordings, and videos
- **Live Web Content**: Public web articles and URLs with automated article extraction

### Deliverable Creation
Generate complete, verified files directly from your source material:
- **Documents**: Structured advisories, executive summaries, technical reports, and briefing memos
- **Presentations**: Multi-slide decks (`.pptx`) with structured headlines, visual recommendations, and speaker notes
- **Spreadsheets**: Data workbooks (`.xlsx`) with organized sheets and calculations
- **Infographics & Posters**: High-resolution visual posters (`.png`) with clean typography and balanced layout
- **Video Packages**: Complete narrated videos (`.mp4`) featuring scene scripts, voice narration, and synchronized subtitles

### Social Media Drafts
Generate platform-optimized social drafts ready for review and publishing:
- **LinkedIn**: Structured posts with engaging hooks, key takeaways, and relevant hashtags
- **X (Twitter)**: Numbered threads adhering strictly to character limits
- **Instagram**: Multi-slide carousel scripts with visual concepts and caption copy
- **Clean Plaintext Copying**: In-app draft cards with one-click copying that automatically strips markdown syntax for direct pasting into social platforms

### Limo Office
Built directly into the desktop workspace:
- View, edit, and format documents, spreadsheets, and presentations natively
- Modify generated files without switching to third-party office applications
- Automatic version tracking whenever files are edited and saved

---

## How It Works

```text
Give Limo your content
        ↓
Tell Limo what you need
        ↓
Limo creates the result
        ↓
Review, edit, and use it
```

1. **Provide Content**: Paste text, attach documents or media files, or provide web links.
2. **Choose Deliverables**: Request a specific deliverable or multiple formats at once (for example, an executive summary, a presentation deck, and a video).
3. **Configure Parameters**: Guide the audience, tone, language, level of detail, and style.
4. **Inspect & Edit**: Review deliverables in the chat feed, watch videos in the embedded player, or open files directly in Limo Office.

---

## Desktop Application

Limo is designed as a desktop-first Electron application, bringing conversational AI, deliverable generation, and Limo Office into a single, cohesive window.

- **Unified Navigation**: Switch seamlessly between the conversational assistant and your office document tabs.
- **Direct File Integration**: Deliverable cards open immediately in the appropriate Limo Office editor.
- **Local File Security**: Files are stored and managed directly on your machine with verified file integrity.

---

## Getting Started

### Prerequisites

Ensure you have the following installed on your system:
- **Node.js**: Version 20 or higher (v22 LTS recommended)
- **Python**: Version 3.11, 3.12, or 3.13
- **FFmpeg**: Required for video rendering and media processing
- **Git**: For repository management

### Quick Start (Windows)

The simplest way to start Limo is using the unified launch script:

```powershell
.\start-all.ps1
```

This launches the backend service, frontend interface, and Limo Office desktop shell in coordinated console windows.

To automatically open the browser once services are ready:

```powershell
.\start-all.ps1 -OpenBrowser
```

### Manual Setup

If you prefer running services individually:

#### 1. Backend Service (FastAPI)

```bash
cd backend
python -m venv .venv

# Activate the virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -e .

# Run the server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### 2. Frontend Interface (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The web interface will be available at `http://localhost:5190`.

#### 3. Limo Office & Desktop Shell (Electron)

```bash
cd engines/office
npm install
npm run dev
```

---

## Project Structure

```text
LIMO/
├── backend/            # FastAPI backend, orchestration runtime, and generation adapters
├── frontend/           # React + TypeScript conversational web application
├── engines/
│   ├── office/         # Limo Office desktop application (Docs, Slides, Sheets)
│   └── video/          # Media and video generation engine
├── skills/             # Modular, file-backed skills (LinkedIn, X, Instagram)
├── docs/               # Architecture guides, specifications, and media assets
│   └── media/          # Video demonstration and branding assets
├── data/               # Sandboxed local storage for sources and generated artifacts
└── start-all.ps1       # Unified application launcher
```

