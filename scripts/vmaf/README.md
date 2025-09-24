# VMAF Video Quality Analysis Tools

A collection of Python scripts for video quality analysis using VMAF (Video Multimethod Assessment Fusion). These tools are designed for testing video encoding/decoding pipelines, synchronization testing, and frame-accurate video quality comparisons.

## Scripts

### 1. `generate_frame_video.py`
**Purpose**: Generate test videos with visible frame numbers for video quality testing.

**Features**:
- Creates videos with large white frame numbers on black backgrounds
- Customizable duration, resolution, and framerate
- Optional concatenation with existing video files
- H.264 encoding with configurable quality settings
- Automatic addition of black frame with "END" marker

**Usage**:
```bash
# Generate a 10-second frame number video
python3 generate_frame_video.py output.mp4

# Generate a 30-second video at 60fps
python3 generate_frame_video.py output.mp4 --duration 30 --fps 60

# Generate at 4K resolution
python3 generate_frame_video.py output.mp4 --width 3840 --height 2160

# Concatenate with existing video
python3 generate_frame_video.py output.mp4 --concat existing_video.mp4

# High quality encoding
python3 generate_frame_video.py output.mp4 --crf 18 --preset slow
```

**Arguments**:
- `output`: Path for the output video file
- `--duration, -d`: Duration in seconds (default: 10)
- `--fps`: Frames per second (default: 30)
- `--width`: Video width in pixels (default: 1920)
- `--height`: Video height in pixels (default: 1080)
- `--concat`: Path to video file to concatenate after frame numbers
- `--preset`: FFmpeg encoding speed preset (default: medium)
- `--crf`: Constant Rate Factor for quality, 0-51 (default: 23)

### 2. `video_sync_vmaf.py`
**Purpose**: Automatically synchronize two videos and perform VMAF quality analysis.

**Features**:
- Detects sync point by identifying frame number transitions
- Trims distorted video with 5-second buffer
- Saves validation frames for manual verification
- Runs VMAF analysis using Docker with easyVmaf
- Outputs results in timestamped directory

**Usage**:
```bash
# Basic usage
python3 video_sync_vmaf.py reference.mp4 distorted.mp4

# With debug logging
python3 video_sync_vmaf.py reference.mp4 distorted.mp4 --debug
```

**Arguments**:
- `reference`: Path to the reference (source) video file
- `distorted`: Path to the distorted (test) video file
- `--debug`: Optional flag to enable verbose debug logging

**Output**: Creates timestamped directory `vmaf_results_<distorted_name>_YYYYMMDD_HHMMSS/` containing:
- Trimmed distorted video aligned with reference
- Validation frame images (PNG)
- VMAF analysis JSON results
- Processing log file

### 3. `plot_vmaf.py`
**Purpose**: Generate visualization plots from VMAF JSON analysis results.

**Features**:
- Creates histogram distributions by quality categories
- Generates frame-by-frame score plots with quality thresholds
- Exports data to TSV format for spreadsheet analysis
- Shows statistics (min, max, mean, harmonic mean)

**Usage**:
```bash
python3 plot_vmaf.py <vmaf_json_file>
```

**Output**:
- `*_histogram.png`: Quality distribution histogram
- `*_frames.png`: Frame-by-frame score plot
- `*_histogram.tsv`: Data export for spreadsheet analysis

**Quality Categories**:
- Excellent (90+): Virtually identical to reference
- Good (74-90): Minor differences
- Fair (58-74): Noticeable but acceptable differences
- Poor (38-58): Significant degradation
- Bad (<38): Very poor quality

## Prerequisites

### Python Dependencies

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### System Requirements

**FFmpeg Installation**:
```bash
# macOS (using Homebrew)
brew install ffmpeg

# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# Windows (using Chocolatey)
choco install ffmpeg

# Or download from: https://ffmpeg.org/download.html
```

**Docker Installation** (required for `video_sync_vmaf.py`):
```bash
# macOS/Windows: Download from https://www.docker.com/products/docker-desktop
# Ubuntu/Debian:
sudo apt update
sudo apt install docker.io
sudo systemctl start docker
sudo systemctl enable docker

# Add your user to docker group (optional, to run without sudo)
sudo usermod -aG docker $USER
# Log out and back in for changes to take effect
```

**VMAF Docker Image**:
```bash
# Pull the easyVMAF Docker image
docker pull gfdavila/easyvmaf

# Verify the image was downloaded
docker images | grep easyvmaf
```

### Verification

Test your setup:
```bash
# Test Python dependencies
python3 -c "import cv2, numpy, matplotlib, easyocr; print('All Python dependencies installed successfully')"

# Test FFmpeg
ffmpeg -version

# Test Docker
docker --version
docker run --rm gfdavila/easyvmaf --help
```

## Video Requirements

For best results with sync detection:
- Videos should contain visible frame numbers (white text on black background)
- Frame numbers should be clearly readable by OCR
- Recommended: 30fps, 1920x1080 resolution
- Supported formats: MP4, MOV, and other FFmpeg-compatible formats

## VMAF Scoring Guide

VMAF scores range from 0-100:
- **90+**: Excellent quality (virtually identical to reference)
- **75-90**: Good quality (minor differences)
- **60-75**: Fair quality (noticeable but acceptable differences)
- **Below 60**: Poor quality (significant degradation)

## Quick Start Commands

**From the project root, run VMAF analysis:**
```bash
# Basic analysis (replace YOUR_VIDEO.mp4 with your actual file)
python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 YOUR_VIDEO.mp4

# With debug logging
python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 YOUR_VIDEO.mp4 --debug

# With custom buffer and seek times
python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 YOUR_VIDEO.mp4 --buffer 3.0 --seek 10.0
```

**Example with common video locations:**
```bash
# If your video is in project root
python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 my-recording.mp4

# If it's in the scripts directory
python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 scripts/my-recording.mp4
```

## Example Workflow

1. **Generate reference video** (optional - one already exists as symlink):
   ```bash
   cd scripts/vmaf
   python3 generate_frame_video.py reference.mp4 --duration 60 --crf 18
   ```

2. **Process your test video** (encode, compress, etc.)

3. **Run VMAF analysis with automatic plot generation**:
   ```bash
   python3 scripts/vmaf/video_sync_vmaf.py scripts/vmaf/reference-video.mp4 your-video.mp4
   ```

The script now automatically generates plots and outputs everything to a timestamped `vmaf_results_*` directory.