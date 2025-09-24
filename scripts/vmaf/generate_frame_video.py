#!/usr/bin/env python3
"""
Test Video Generator with Frame Numbers

DESCRIPTION:
    Generates test videos with visible frame numbers for video quality testing and
    synchronization. Creates videos with large white frame numbers on a black background,
    ideal for:
    - Testing video encoding/decoding pipelines
    - Synchronization testing between multiple video streams
    - Frame-accurate video quality comparisons
    - VMAF analysis preparation

    The tool can also concatenate the generated frame video with existing videos,
    useful for adding sync markers to test content.

FEATURES:
    - Generate videos with customizable duration, resolution, and framerate
    - Large, clear frame numbers for easy OCR detection
    - Optional concatenation with existing video files
    - H.264 encoding with configurable quality settings
    - Automatic addition of black frame with "END" marker

PREREQUISITES:
    # System requirements:
    - FFmpeg must be installed (for H.264 encoding and concatenation)

USAGE:
    # Generate a 10-second frame number video:
    python3 generate_frame_video.py output.mp4

    # Generate a 30-second video at 60fps:
    python3 generate_frame_video.py output.mp4 --duration 30 --fps 60

    # Generate at 4K resolution:
    python3 generate_frame_video.py output.mp4 --width 3840 --height 2160

    # Concatenate with existing video:
    python3 generate_frame_video.py output.mp4 --concat existing_video.mp4

    # High quality encoding (lower CRF = better quality):
    python3 generate_frame_video.py output.mp4 --crf 18 --preset slow

ARGUMENTS:
    output: Path for the output video file
    --duration, -d: Duration in seconds (default: 10)
    --fps: Frames per second (default: 30)
    --width: Video width in pixels (default: 1920)
    --height: Video height in pixels (default: 1080)
    --concat: Path to video file to concatenate after frame numbers
    --preset: FFmpeg encoding speed preset (default: medium)
              Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    --crf: Constant Rate Factor for quality, 0-51 (default: 23)
           Lower values = better quality but larger file size

OUTPUT:
    Creates an H.264 encoded MP4 file containing:
    - Frame numbers from 1 to (duration * fps)
    - Optional concatenated video content
    - Black frame with "END" marker at the end

EXAMPLES:
    # Quick test video for development:
    python3 generate_frame_video.py test.mp4 --duration 5 --preset ultrafast

    # High-quality reference video for VMAF testing:
    python3 generate_frame_video.py reference.mp4 --duration 60 --crf 18 --preset slow

    # Add frame numbers to existing content:
    python3 generate_frame_video.py marked_content.mp4 --duration 10 --concat content.mp4

NOTE:
    Frame numbers are rendered in white text on black background using OpenCV's
    FONT_HERSHEY_SIMPLEX font at size 8 with thickness 15 for maximum readability.
"""
import cv2
import numpy as np
import argparse
import subprocess
import os
from pathlib import Path

def generate_frame_video(output_path, duration_seconds=10, fps=30, width=1920, height=1080):
    """Generate a video with frame numbers on black background."""

    # Calculate total frames
    total_frames = duration_seconds * fps

    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"Generating {duration_seconds}s video at {fps}fps ({total_frames} frames)")
    print(f"Resolution: {width}x{height}")
    print(f"Output: {output_path}")

    for frame_num in range(1, total_frames + 1):
        # Create black frame
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Add frame number text
        text = str(frame_num)

        # Calculate text size and position
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 8  # Large font
        thickness = 15

        # Get text size
        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        # Center the text
        x = (width - text_width) // 2
        y = (height + text_height) // 2

        # Draw white text
        cv2.putText(frame, text, (x, y), font, font_scale, (255, 255, 255), thickness)

        # Write frame
        out.write(frame)

        # Progress indicator
        if frame_num % 30 == 0 or frame_num == total_frames:
            progress = (frame_num / total_frames) * 100
            print(f"Progress: {progress:.1f}% (frame {frame_num}/{total_frames})")

    # Release everything
    out.release()
    print(f"Video generated successfully: {output_path}")

def convert_to_h264(input_path, output_path, preset="medium", crf=23):
    """Convert video to H.264 format."""
    print(f"Converting to H.264 format...")

    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-c:v', 'libx264',
        '-preset', preset,
        '-crf', str(crf),
        '-y',  # Overwrite output
        output_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"H.264 conversion successful: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"H.264 conversion failed: {e}")
        return False

def create_black_frame_video(output_path, fps=30, width=1920, height=1080):
    """Create a single black frame video with 'END' text."""
    print(f"Creating single black frame video with 'END' text: {output_path}")

    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Create black frame
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # Add "END" text in white
    text = "END"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 8  # Large font to match frame numbers
    thickness = 15

    # Get text size
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    # Center the text
    x = (width - text_width) // 2
    y = (height + text_height) // 2

    # Draw white text
    cv2.putText(frame, text, (x, y), font, font_scale, (255, 255, 255), thickness)

    # Write the single black frame with END text
    out.write(frame)

    # Release everything
    out.release()
    print(f"Black frame video with 'END' text created: {output_path}")

def create_black_duration_video(output_path, duration_seconds=10, fps=30, width=1920, height=1080):
    """Create a video of black frames for specified duration."""
    print(f"Creating {duration_seconds}s black video: {output_path}")

    # Define the codec and create VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Calculate total frames
    total_frames = duration_seconds * fps

    # Create black frame
    frame = np.zeros((height, width, 3), dtype=np.uint8)

    # Write black frames for the duration
    for _ in range(total_frames):
        out.write(frame)

    # Release everything
    out.release()
    print(f"Black duration video created: {output_path}")

def concatenate_videos(frame_video_path, target_video_path, output_path, preset="medium", crf=23, with_10s_black=False):
    """Concatenate frame video with target video and add one black frame at the end."""
    print(f"Concatenating videos with black frame at end...")

    # Get video dimensions from the frame video
    import cv2
    cap = cv2.VideoCapture(frame_video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    # Create a single black frame video with matching dimensions
    black_frame_video = "temp_black_frame.mp4"
    create_black_frame_video(black_frame_video, fps, width, height)

    # Convert black frame to H.264
    black_frame_h264 = "temp_black_frame_h264.mp4"
    if not convert_to_h264(black_frame_video, black_frame_h264, preset, crf):
        print("Failed to convert black frame to H.264")
        return False

    # Clean up original black frame
    os.remove(black_frame_video)

    # Create temporary concat list with black frame at the end
    concat_list = "temp_concat_list.txt"
    with open(concat_list, 'w') as f:
        f.write(f"file '{frame_video_path}'\n")
        f.write(f"file '{target_video_path}'\n")
        f.write(f"file '{black_frame_h264}'\n")

    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_list,
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-preset', preset,
        '-crf', str(crf),
        '-y',  # Overwrite output
        output_path
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"Concatenation successful: {output_path}")

        # Clean up temp files
        os.remove(concat_list)
        os.remove(black_frame_h264)
        return True

    except subprocess.CalledProcessError as e:
        print(f"Concatenation failed: {e}")
        print(f"FFmpeg stderr: {e.stderr}")
        if os.path.exists(concat_list):
            os.remove(concat_list)
        if os.path.exists(black_frame_h264):
            os.remove(black_frame_h264)
        return False

def main():
    parser = argparse.ArgumentParser(description='Generate test video with frame numbers and optionally concatenate')
    parser.add_argument('output', help='Output video file path')
    parser.add_argument('--duration', '-d', type=int, default=10, help='Duration in seconds (default: 10)')
    parser.add_argument('--fps', type=int, default=30, help='Frames per second (default: 30)')
    parser.add_argument('--width', type=int, default=1920, help='Video width (default: 1920)')
    parser.add_argument('--height', type=int, default=1080, help='Video height (default: 1080)')
    parser.add_argument('--concat', help='Video file to concatenate after the frame video')
    parser.add_argument('--preset', default='medium', choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'], help='FFmpeg encoding preset (default: medium)')
    parser.add_argument('--crf', type=int, default=23, help='Constant Rate Factor for quality (lower = better quality, default: 23)')

    args = parser.parse_args()

    # Generate base frame video
    temp_frame_video = "temp_frame_video.mp4"
    generate_frame_video(temp_frame_video, args.duration, args.fps, args.width, args.height)

    # Convert to H.264
    frame_video_h264 = "temp_frame_video_h264.mp4"
    if not convert_to_h264(temp_frame_video, frame_video_h264, args.preset, args.crf):
        print("Failed to convert frame video to H.264")
        return

    # Clean up original MPEG-4 file
    os.remove(temp_frame_video)

    if args.concat:
        # Concatenate with target video
        if not os.path.exists(args.concat):
            print(f"Target video not found: {args.concat}")
            return

        # Create output
        if not concatenate_videos(frame_video_h264, args.concat, args.output, args.preset, args.crf):
            print("Failed to concatenate videos")
            return
        print(f"Final concatenated video: {args.output}")

        # Clean up temp H.264 file
        os.remove(frame_video_h264)

    else:
        # Just save the frame video
        os.rename(frame_video_h264, args.output)
        print(f"Final frame video: {args.output}")

if __name__ == '__main__':
    main()