# FrameForge

**A Professional PNG Sequence Encoder for High-Quality Video Workflows.**

FrameForge is a desktop application designed to convert PNG image sequences into high-quality video files using FFmpeg.

Built for creators and technical workflows, it provides precise control over frame ranges, frame rates, encoding formats, and image sequence validation. It is particularly suited for animation rendering, compositing, and post-production workflows where image fidelity and alpha channel preservation matter.

## Features

- **PNG Sequence Processing** — Automatically detects numbered PNG image sequences.
- **Flexible Frame Selection** — Specify custom start and end frames.
- **Custom Frame Rate** — Configure the output frame rate for precise timing.
- **Lossless Encoding** — Export using FFV1 or QuickTime PNG to preserve image quality.
- **Alpha Channel Support** — Preserve transparency when using compatible output formats.
- **16-bit PNG Support** — Designed to handle high-bit-depth PNG sequences.
- **Professional Output Formats** — Supports multiple encoding workflows:
  - QuickTime PNG (`.mov`)
  - FFV1 (`.mkv`)
  - ProRes 4444 (`.mov`)
- **Sequence Validation** — Checks image dimensions and frame integrity before encoding.
- **Output Verification** — Uses FFprobe to verify the generated video.
- **Safe Export Process** — Writes to a temporary output file and renames it only after successful encoding.
- **Encoding Logs** — Provides processing feedback and diagnostic information.

## Supported Workflows

| Workflow | Recommended Format |
|---|---|
| Lossless image sequence archiving | FFV1 / MKV |
| QuickTime-based post-production | PNG / MOV |
| Alpha-enabled editing workflows | ProRes 4444 / MOV |
| High-bit-depth image sequences | Depends on source and encoder compatibility |

*Actual format capabilities depend on the source images and FFmpeg encoder configuration.*

## Requirements

- Windows
- Python
- PyQt5
- FFmpeg
- FFprobe

Make sure FFmpeg and FFprobe are installed and accessible through your system's PATH.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/XingAnDev/FrameForge.git
cd FrameForge
```

### 2. Install dependencies

```bash
pip install PyQt5
```

Install FFmpeg separately and ensure that both `ffmpeg` and `ffprobe` can be executed from the command line.

### 3. Launch FrameForge

```bash
python png_to_video.py
```

## Intended Use

FrameForge is designed for workflows involving:

- Blender animation and rendering
- MMD animation production
- DaVinci Resolve post-production
- Compositing and visual effects
- PNG-based image sequence archiving

It aims to provide a reliable bridge between rendered image sequences and professional video editing workflows.

## Technology Stack

- **Python** — Application logic
- **PyQt5** — Desktop graphical interface
- **FFmpeg** — Video encoding
- **FFprobe** — Output inspection and validation

## Project Philosophy

FrameForge focuses on three principles:

**Image Integrity.**
