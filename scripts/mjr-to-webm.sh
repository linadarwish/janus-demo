#!/bin/bash

# mjr-to-webm.sh
# Post-processes Janus .mjr files to extract video (.webm) or audio (.opus) files
# Requires janus-pp-rec tool from Janus Gateway

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 <mjr-file> [output-file]"
    echo ""
    echo "Converts Janus .mjr recording files to .webm (video) or .opus (audio) format"
    echo ""
    echo "Arguments:"
    echo "  mjr-file     Input .mjr file to convert"
    echo "  output-file  Optional output file (auto-detects .webm/.opus if not specified)"
    echo ""
    echo "Examples:"
    echo "  $0 recording-video.mjr                    # Output: recording-video.webm"
    echo "  $0 recording-audio.mjr                    # Output: recording-audio.opus"
    echo "  $0 recording-video.mjr my-video.webm     # Custom output name"
    echo ""
    echo "File Type Detection:"
    echo "  - Automatically detects audio vs video from .mjr file content"
    echo "  - Audio files are converted to .opus format"
    echo "  - Video files are converted to .webm format"
    echo ""
    echo "Requirements:"
    echo "  - janus-pp-rec tool (from Janus Gateway installation)"
    echo "  - Docker with janus-demo container running"
}

# Check if help was requested
if [[ "$1" == "-h" || "$1" == "--help" || $# -eq 0 ]]; then
    show_usage
    exit 0
fi

# Check arguments
if [[ $# -lt 1 ]]; then
    print_error "Missing required argument: mjr-file"
    show_usage
    exit 1
fi

INPUT_FILE="$1"

# Detect if this is an audio or video file by checking the content
print_info "Analyzing $INPUT_FILE to determine audio/video type..."

# Use janus-pp-rec to detect file type
if docker ps --filter "name=janus-demo" --format "table {{.Names}}" | grep -q "janus-demo"; then
    # Copy file to container for analysis
    docker cp "$INPUT_FILE" janus-demo:/tmp/analyze.mjr

    # Run janus-pp-rec to analyze the file (it will show the type in output)
    ANALYSIS_OUTPUT=$(docker exec janus-demo janus-pp-rec /tmp/analyze.mjr /tmp/test.out 2>&1 || true)

    # Clean up analysis files
    docker exec janus-demo rm -f /tmp/analyze.mjr /tmp/test.out

    if echo "$ANALYSIS_OUTPUT" | grep -q "This is an audio recording"; then
        FILE_TYPE="audio"
        DEFAULT_EXTENSION="opus"
    elif echo "$ANALYSIS_OUTPUT" | grep -q "This is a video recording"; then
        FILE_TYPE="video"
        DEFAULT_EXTENSION="webm"
    else
        print_warning "Could not determine file type, assuming video"
        FILE_TYPE="video"
        DEFAULT_EXTENSION="webm"
    fi
else
    # If container not available, guess from filename
    if [[ "$INPUT_FILE" == *"audio"* ]]; then
        FILE_TYPE="audio"
        DEFAULT_EXTENSION="opus"
    else
        FILE_TYPE="video"
        DEFAULT_EXTENSION="webm"
    fi
fi

# Set output file with correct extension
if [[ -n "$2" ]]; then
    OUTPUT_FILE="$2"
else
    OUTPUT_FILE="${INPUT_FILE%.mjr}.${DEFAULT_EXTENSION}"
fi

print_info "Detected: $FILE_TYPE file, output will be: $OUTPUT_FILE"

# Check if input file exists
if [[ ! -f "$INPUT_FILE" ]]; then
    print_error "Input file does not exist: $INPUT_FILE"
    exit 1
fi

# Check if input file has .mjr extension
if [[ "$INPUT_FILE" != *.mjr ]]; then
    print_error "Input file must have .mjr extension: $INPUT_FILE"
    exit 1
fi

print_info "Converting $INPUT_FILE to $OUTPUT_FILE"

# Determine output extension for temporary file
if [[ "$FILE_TYPE" == "audio" ]]; then
    TEMP_OUTPUT="/tmp/output.opus"
else
    TEMP_OUTPUT="/tmp/output.webm"
fi

# Check if janus-pp-rec is available locally
if command -v janus-pp-rec &> /dev/null; then
    print_info "Using local janus-pp-rec tool"
    janus-pp-rec "$INPUT_FILE" "$OUTPUT_FILE"
elif docker ps --filter "name=janus-demo" --format "table {{.Names}}" | grep -q "janus-demo"; then
    print_info "Using janus-pp-rec from janus-demo container"

    # Copy file to container
    print_info "Copying $INPUT_FILE to container..."
    docker cp "$INPUT_FILE" janus-demo:/tmp/input.mjr

    # Run conversion inside container with correct output format
    print_info "Running $FILE_TYPE conversion..."
    docker exec janus-demo janus-pp-rec /tmp/input.mjr "$TEMP_OUTPUT"

    # Copy result back
    print_info "Copying result back..."
    docker cp "janus-demo:$TEMP_OUTPUT" "$OUTPUT_FILE"

    # Clean up temporary files in container
    docker exec janus-demo rm -f /tmp/input.mjr "$TEMP_OUTPUT"
else
    print_error "janus-pp-rec tool not found and janus-demo container not running"
    print_error "Please install Janus Gateway or start the janus-demo container"
    exit 1
fi

if [[ -f "$OUTPUT_FILE" ]]; then
    print_info "Conversion successful: $OUTPUT_FILE"

    # Show file size
    if command -v du &> /dev/null; then
        INPUT_SIZE=$(du -h "$INPUT_FILE" | cut -f1)
        OUTPUT_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        print_info "File sizes - Input: $INPUT_SIZE, Output: $OUTPUT_SIZE"
    fi
else
    print_error "Conversion failed - output file not created"
    exit 1
fi