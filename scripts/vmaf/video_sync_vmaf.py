#!/usr/bin/env python3
"""
Video Sync Detection and VMAF Quality Analysis Tool

DESCRIPTION:
    Automatically synchronizes two videos and performs VMAF (Video Multimethod Assessment
    Fusion) quality analysis. This tool is designed for comparing a reference video with
    a distorted/processed version when both contain visible frame numbers.

    The script performs the following operations:
    1. Detects sync point by identifying frame number transitions in the distorted video
    2. Trims the distorted video at the detected sync point with a 5-second buffer
    3. Saves validation frames for manual verification
    4. Runs VMAF analysis using Docker with easyVmaf to compare video quality
    5. Generates VMAF visualization plots (histogram and frame-by-frame charts)
    6. Outputs all results in a timestamped directory

PREREQUISITES:
    # Docker image for VMAF analysis:
    docker pull gfdavila/easyvmaf

    # System requirements:
    - Docker must be installed and running
    - FFmpeg must be installed (for video trimming)
    - Sufficient disk space for video processing

USAGE:
    # Basic usage:
    python3 video_sync_vmaf.py reference.mp4 distorted.mp4

    # With debug logging for troubleshooting:
    python3 video_sync_vmaf.py reference.mp4 distorted.mp4 --debug

    # With custom buffer time:
    python3 video_sync_vmaf.py reference.mp4 distorted.mp4 --buffer 3.0

    # Skip first 10 seconds when looking for numbered frames:
    python3 video_sync_vmaf.py reference.mp4 distorted.mp4 --seek-distorted 10.0

ARGUMENTS:
    reference: Path to the reference (source) video file
    distorted: Path to the distorted (test) video file
    --debug: Optional flag to enable verbose debug logging
    --buffer: Buffer time in seconds after sync point (default: 5.0)
    --seek-distorted: Skip this many seconds when looking for numbered frames in distorted video (default: 0.0)

OUTPUT:
    Creates a timestamped directory: vmaf_results_<distorted_name>_YYYYMMDD_HHMMSS/
    containing:
    - Trimmed distorted video aligned with reference
    - Validation frame images (PNG)
    - VMAF analysis JSON results
    - VMAF visualization plots (histogram and frame-by-frame charts)
    - CSV data for spreadsheet analysis
    - Processing log file
    - Debug frames (if issues detected)

VIDEO REQUIREMENTS:
    - Reference video should have frame numbers visible (white text on black background)
    - Frame numbers should be clearly readable by OCR
    - Videos should be in a format supported by FFmpeg (MP4, MOV, etc.)
    - Recommended: 30fps, 1920x1080 resolution for best results

VMAF SCORING:
    VMAF scores range from 0-100:
    - 90+: Excellent quality (virtually identical to reference)
    - 75-90: Good quality (minor differences)
    - 60-75: Fair quality (noticeable but acceptable differences)
    - Below 60: Poor quality (significant degradation)

EXAMPLE:
    python3 video_sync_vmaf.py original.mp4 compressed.mp4

    This will:
    1. Find where compressed.mp4 syncs with original.mp4
    2. Trim compressed.mp4 to align properly
    3. Run VMAF analysis between the synchronized videos
    4. Output quality metrics in JSON format
"""

import cv2
import numpy as np
import subprocess
import sys
import os
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime
import easyocr

logger = logging.getLogger(__name__)

def setup_logging(log_file_path, debug=False):
    """Setup logging to both console and file."""
    # Clear any existing handlers
    logger.handlers.clear()

    # Set logger level
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file_path, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False

class VideoSyncVMAF:
    def __init__(self, reference_path, distorted_path, buffer_seconds=5.0, seek_distorted=0.0):
        self.reference_path = Path(reference_path)
        self.distorted_path = Path(distorted_path)
        self.buffer_seconds = buffer_seconds
        self.seek_distorted = seek_distorted

        # Create timestamped directory for results with distorted filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        distorted_name = self.distorted_path.stem
        self.results_dir = Path(f"vmaf_results_{distorted_name}_{timestamp}")
        self.results_dir.mkdir(exist_ok=True)

        # Set paths within the timestamped directory - preserve original format
        original_suffix = self.distorted_path.suffix
        self.trimmed_path = self.results_dir / f"{self.distorted_path.stem}-trimmed{original_suffix}"
        self.results_log = self.results_dir / "results.log"

        # Setup logging to file and console
        setup_logging(self.results_log)

        logger.info(f"Created results directory: {self.results_dir}")

        if not self.reference_path.exists():
            raise FileNotFoundError(f"Reference video not found: {self.reference_path}")
        if not self.distorted_path.exists():
            raise FileNotFoundError(f"Distorted video not found: {self.distorted_path}")

        logger.info(f"Reference video: {self.reference_path}")
        logger.info(f"Distorted video: {self.distorted_path}")
        logger.info(f"Output trimmed video: {self.trimmed_path}")
        logger.info(f"Results log: {self.results_log}")
        logger.info(f"Buffer time: {self.buffer_seconds}s")
        logger.info(f"Seek distorted: {self.seek_distorted}s")

        # Initialize EasyOCR reader
        logger.info("Initializing EasyOCR...")
        self.ocr_reader = easyocr.Reader(['en'])

    def extract_frame_number(self, frame):
        """Extract frame number from a frame using EasyOCR."""
        if frame is None:
            return None

        try:
            # Use EasyOCR with digit allowlist
            results = self.ocr_reader.readtext(frame, allowlist='0123456789')

            if results:
                # Take the result with highest confidence
                best_result = max(results, key=lambda x: x[2])
                bbox, text, confidence = best_result

                logger.debug(f"EasyOCR extracted: '{text}' (conf: {confidence:.3f})")

                if text.isdigit():
                    logger.debug(f"Successfully extracted number: {int(text)}")
                    return int(text)

            # If OCR fails, save the frame for debugging
            debug_path = self.results_dir / f"debug_frame_{hash(frame.tobytes()) % 10000}.png"
            cv2.imwrite(str(debug_path), frame)
            logger.debug(f"EasyOCR failed, saved debug frame: {debug_path}")

            return None

        except Exception as e:
            logger.warning(f"EasyOCR extraction failed: {e}")
            return None

    def extract_frame_number_with_confidence(self, frame):
        """Extract frame number from a frame using EasyOCR, returning both number and confidence."""
        if frame is None:
            return None, 0.0

        try:
            # Use EasyOCR with digit allowlist
            results = self.ocr_reader.readtext(frame, allowlist='0123456789')

            if results:
                # Take the result with highest confidence
                best_result = max(results, key=lambda x: x[2])
                bbox, text, confidence = best_result

                logger.debug(f"EasyOCR extracted: '{text}' (conf: {confidence:.3f})")

                if text.isdigit():
                    logger.debug(f"Successfully extracted number: {int(text)} with confidence {confidence:.3f}")
                    return int(text), confidence

            return None, 0.0

        except Exception as e:
            logger.warning(f"EasyOCR extraction failed: {e}")
            return None, 0.0

    def find_sync_point(self, video_path):
        """Find the timestamp where frame number changes with both numbers detected at >50% confidence."""
        logger.info(f"Analyzing video for sync point: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        logger.info(f"Video properties - FPS: {fps:.2f}, Total frames: {total_frames}, Duration: {duration:.2f}s")

        # Skip to seek position if specified
        if self.seek_distorted > 0:
            seek_frame = int(self.seek_distorted * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, seek_frame)
            logger.info(f"Seeking to {self.seek_distorted}s (frame {seek_frame})")

        frame_count = int(self.seek_distorted * fps) if self.seek_distorted > 0 else 0
        last_frame_number = None
        last_confidence = None
        sync_timestamp = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_count / fps
            frame_number, confidence = self.extract_frame_number_with_confidence(frame)

            # Log every frame being analyzed
            if frame_number is not None:
                logger.info(f"Frame {frame_count} at {current_time:.3f}s: {frame_number} (conf: {confidence:.3f})")
            else:
                logger.info(f"Frame {frame_count} at {current_time:.3f}s: no number detected")

            # Only consider detections with confidence > 50%
            if frame_number is not None and confidence > 0.5:
                # Check for frame number change with both having high confidence
                if (last_frame_number is not None and last_confidence is not None and
                    last_confidence > 0.5 and last_frame_number != frame_number):

                    logger.info(f"→ Frame number changed: {last_frame_number} (conf: {last_confidence:.3f}) → {frame_number} (conf: {confidence:.3f})")

                    # Use any frame transition as sync point, not just 1→2
                    sync_timestamp = current_time
                    logger.info(f"✓ Found sync point: frame {last_frame_number}→{frame_number} transition at {sync_timestamp:.3f}s")
                    break

                last_frame_number = frame_number
                last_confidence = confidence

            frame_count += 1

            # Safety break to avoid infinite loops (30 seconds from seek point)
            if frame_count > (self.seek_distorted + 30) * fps:  # Don't analyze more than 30 seconds from seek point
                logger.warning("Reached 30-second limit without finding sync point")
                break

        cap.release()

        if sync_timestamp is None:
            logger.warning("Could not find sync point automatically. Using fallback method.")
            sync_timestamp = self.find_sync_point_fallback(video_path)

        return sync_timestamp

    def find_sync_point_fallback(self, video_path):
        """Fallback method using frame difference analysis."""
        logger.info("Using fallback frame difference analysis")

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # Skip to seek position if specified
        if self.seek_distorted > 0:
            seek_frame = int(self.seek_distorted * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, seek_frame)
            logger.info(f"Seeking to {self.seek_distorted}s (frame {seek_frame}) for fallback analysis")

        frame_count = int(self.seek_distorted * fps) if self.seek_distorted > 0 else 0
        prev_frame = None
        max_diff = 0
        sync_frame = frame_count
        analyze_frames = frame_count + int(fps * 10)  # Analyze 10 seconds from seek point

        logger.info(f"Analyzing frames {frame_count} to {analyze_frames} for maximum difference")

        while frame_count < analyze_frames:
            ret, frame = cap.read()
            if not ret:
                break

            if prev_frame is not None:
                # Calculate frame difference
                gray_curr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
                diff = cv2.absdiff(gray_curr, gray_prev)
                diff_score = np.sum(diff)

                if diff_score > max_diff:
                    max_diff = diff_score
                    sync_frame = frame_count
                    logger.debug(f"New max difference at frame {frame_count}: {diff_score}")

            prev_frame = frame
            frame_count += 1

            # Progress indicator
            if frame_count % int(fps) == 0:
                logger.info(f"Analyzed {frame_count - int(self.seek_distorted * fps)}/{analyze_frames - int(self.seek_distorted * fps)} frames")

        cap.release()

        sync_timestamp = sync_frame / fps
        logger.info(f"Fallback sync point found at frame {sync_frame} ({sync_timestamp:.3f}s) with diff score: {max_diff}")
        return sync_timestamp

    def get_first_frame_number(self):
        """Get the first frame number from the trimmed video and save validation frames."""
        logger.info(f"Analyzing first frame of trimmed video: {self.trimmed_path}")

        if not self.trimmed_path.exists():
            logger.error("Trimmed video file does not exist")
            return None

        cap = cv2.VideoCapture(str(self.trimmed_path))
        if not cap.isOpened():
            logger.error("Could not open trimmed video file")
            return None

        # Read the first frame
        ret, frame = cap.read()
        cap.release()

        if not ret:
            logger.error("Could not read first frame from trimmed video")
            return None

        # Save first frame of trimmed video for validation
        trimmed_first_frame_path = self.results_dir / "trimmed_first_frame.png"
        cv2.imwrite(str(trimmed_first_frame_path), frame)
        logger.info(f"Saved first frame of trimmed video: {trimmed_first_frame_path}")

        # Extract frame number from first frame using EasyOCR
        try:
            results = self.ocr_reader.readtext(frame, allowlist='0123456789')

            if results:
                best_result = max(results, key=lambda x: x[2])
                bbox, text, confidence = best_result
                logger.info(f"EasyOCR on first frame extracted: '{text}' (conf: {confidence:.3f})")

                if text.isdigit():
                    frame_number = int(text)
                    logger.info(f"First frame number detected: {frame_number}")
                else:
                    logger.warning(f"EasyOCR extracted non-digit text: '{text}'")
                    frame_number = None
            else:
                logger.warning("No text detected by EasyOCR")
                frame_number = None
        except Exception as e:
            logger.warning(f"EasyOCR failed: {e}")
            frame_number = None

        if frame_number is None:
            logger.warning("Could not detect frame number in first frame")

            # Analyze the frame content
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

            # Check if frame is mostly black
            mean_brightness = np.mean(gray)
            max_brightness = np.max(gray)
            white_pixels = np.sum(gray > 200)
            total_pixels = gray.shape[0] * gray.shape[1]

            logger.info(f"Frame analysis - Mean brightness: {mean_brightness:.1f}, Max brightness: {max_brightness}")
            logger.info(f"White pixels (>200): {white_pixels}/{total_pixels} ({100*white_pixels/total_pixels:.1f}%)")

            # Save debug frames
            debug_path = self.results_dir / "debug_trimmed_first_frame_gray.png"
            cv2.imwrite(str(debug_path), gray)
            logger.info(f"Saved debug grayscale frame: {debug_path}")

            # Try EasyOCR on grayscale
            try:
                results = self.ocr_reader.readtext(gray, allowlist='0123456789')
                if results:
                    best_result = max(results, key=lambda x: x[2])
                    bbox, text, confidence = best_result
                    logger.info(f"EasyOCR grayscale result: '{text}' (conf: {confidence:.3f})")
                else:
                    logger.info("No text detected by EasyOCR on grayscale")
            except Exception as e:
                logger.warning(f"EasyOCR grayscale failed: {e}")

        return frame_number

    def find_frame_in_original_video(self, target_frame_number):
        """Find the frame number in reference video by scanning frame by frame."""
        logger.info(f"Searching for frame number {target_frame_number} in reference video: {self.reference_path.name}")

        cap = cv2.VideoCapture(str(self.reference_path))
        if not cap.isOpened():
            logger.error(f"Could not open reference video for frame search: {self.reference_path.name}")
            return None

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = 0

        while frame_count < int(fps * 60):  # Limit to first 60 seconds
            ret, frame = cap.read()
            if not ret:
                break

            current_time = frame_count / fps

            # Use EasyOCR to detect frame number
            results = self.ocr_reader.readtext(frame, allowlist='0123456789')
            detected_number = None

            if results:
                best_result = max(results, key=lambda x: x[2])
                bbox, text, confidence = best_result
                if text.isdigit():
                    detected_number = int(text)

            # Log every frame for debugging
            logger.info(f"[{self.reference_path.name}] Frame {frame_count} at {current_time:.3f}s: {detected_number if detected_number else 'no number'}")

            if detected_number == target_frame_number:
                logger.info(f"✓ Found target frame {target_frame_number} at frame {frame_count} ({current_time:.3f}s) in {self.reference_path.name}")
                cap.release()
                return frame_count

            frame_count += 1

        cap.release()
        logger.warning(f"Could not find frame {target_frame_number} in first 60 seconds of {self.reference_path.name}")
        return None

    def save_reference_frame_at_position(self, frame_position, frame_number):
        """Save a frame from the reference video at the found frame position."""
        logger.info(f"Saving frame {frame_number} from reference video at position {frame_position}")

        cap = cv2.VideoCapture(str(self.reference_path))
        if not cap.isOpened():
            logger.error(f"Could not open reference video: {self.reference_path.name}")
            return

        # Seek to the specific frame position
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
        ret, frame = cap.read()
        cap.release()

        if ret:
            reference_frame_path = self.results_dir / f"reference_frame_{frame_number}_at_position_{frame_position}.png"
            cv2.imwrite(str(reference_frame_path), frame)
            logger.info(f"Saved reference frame: {reference_frame_path}")
        else:
            logger.warning(f"Could not read frame at position {frame_position} from reference video")

    def copy_distorted_file(self):
        """Copy the original distorted file to the results directory."""
        logger.info(f"Copying distorted file to results directory")

        # Define destination path in results directory
        distorted_copy_path = self.results_dir / self.distorted_path.name

        try:
            # Use subprocess to copy the file (cross-platform)
            if os.name == 'nt':  # Windows
                subprocess.run(['copy', str(self.distorted_path), str(distorted_copy_path)],
                             shell=True, check=True)
            else:  # Unix/Linux/macOS
                subprocess.run(['cp', str(self.distorted_path), str(distorted_copy_path)],
                             check=True)

            logger.info(f"✓ Distorted file copied to: {distorted_copy_path}")

            # Log file size
            if distorted_copy_path.exists():
                size_mb = distorted_copy_path.stat().st_size / (1024 * 1024)
                logger.info(f"Copied distorted file size: {size_mb:.1f} MB")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"✗ Failed to copy distorted file: {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Error copying distorted file: {e}")
            return False

    def trim_video(self, offset_seconds):
        """Trim the distorted video at the calculated offset with configurable buffer."""
        start_time = max(0, round(offset_seconds) + self.buffer_seconds)

        logger.info(f"Trimming video from {start_time:.1f}s (offset: {offset_seconds:.3f}s, buffer: {self.buffer_seconds}s)")
        logger.info(f"Input: {self.distorted_path}")
        logger.info(f"Output: {self.trimmed_path}")

        cmd = [
            'ffmpeg',
            '-ss', str(int(start_time)),  # Seek before input for keyframe accuracy
            '-i', str(self.distorted_path),
            '-c', 'copy',  # Copy streams without re-encoding
            '-avoid_negative_ts', 'make_zero',
            '-y',  # Overwrite output file
            str(self.trimmed_path)
        ]

        logger.info(f"FFmpeg command: {' '.join(cmd)}")

        try:
            logger.info("Executing FFmpeg command...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            logger.info(f"✓ Video trimmed successfully: {self.trimmed_path}")

            # Log output file info
            if self.trimmed_path.exists():
                size_mb = self.trimmed_path.stat().st_size / (1024 * 1024)
                logger.info(f"Trimmed video size: {size_mb:.1f} MB")

            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ FFmpeg error: {e}")
            logger.error(f"FFmpeg stdout: {e.stdout}")
            logger.error(f"FFmpeg stderr: {e.stderr}")
            return False

    def run_vmaf_analysis(self, timestamp_offset):
        """Run VMAF analysis using Docker with easyVmaf."""
        logger.info(f"🚀 Starting VMAF analysis with Docker from timestamp {timestamp_offset:.6f}s")

        # Mount directories for Docker access
        current_dir = os.getcwd()
        resolved_reference = self.reference_path.resolve()
        reference_dir = resolved_reference.parent

        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{current_dir}:/videos',
            '-v', f'{reference_dir}:/reference',
            'gfdavila/easyvmaf',
            '-r', f'/reference/{resolved_reference.name}',
            '-d', f'/videos/{self.results_dir.name}/{self.trimmed_path.name}',
            '-ss', str(timestamp_offset),
            '-endsync',
            '-output_fmt', 'json'
        ]

        logger.info(f"Docker timestamp offset: {timestamp_offset:.6f}s")
        logger.info(f"Docker command: {' '.join(cmd)}")

        try:
            logger.info("Starting Docker container...")

            # Run Docker command
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, universal_newlines=True)

            line_count = 0
            for line in process.stdout:
                line_count += 1
                logger.info(f"Docker: {line.strip()}")

                # Log progress periodically
                if line_count % 100 == 0:
                    logger.info(f"Docker output: {line_count} lines processed")

            process.wait()

            if process.returncode == 0:
                logger.info("✓ VMAF analysis completed successfully")

                # Look for generated VMAF files
                vmaf_files = list(self.results_dir.parent.glob("*vmaf*.json"))
                if vmaf_files:
                    for vmaf_file in vmaf_files:
                        new_path = self.results_dir / vmaf_file.name
                        vmaf_file.rename(new_path)
                        logger.info(f"Moved VMAF result to: {new_path}")

                return True
            else:
                logger.error(f"✗ Docker command failed with return code {process.returncode}")
                return False

        except Exception as e:
            logger.error(f"✗ Error running VMAF analysis: {e}")
            return False

    def generate_vmaf_plots(self):
        """Generate VMAF plots by running the plot_vmaf.py script on the JSON results."""
        logger.info("Searching for VMAF JSON files to plot")

        # Look for VMAF JSON files in the results directory
        vmaf_json_files = list(self.results_dir.glob("*vmaf*.json"))

        if not vmaf_json_files:
            logger.error("✗ No VMAF JSON files found for plotting")
            return False

        # Get the path to the plot_vmaf.py script
        plot_script_path = Path(__file__).parent / "plot_vmaf.py"

        if not plot_script_path.exists():
            logger.error(f"✗ Plot script not found: {plot_script_path}")
            return False

        success = True
        for json_file in vmaf_json_files:
            logger.info(f"Generating plots for: {json_file}")

            cmd = [
                'python3',
                str(plot_script_path),
                str(json_file)
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                logger.info(f"✓ Plot generation output for {json_file.name}:")
                for line in result.stdout.strip().split('\n'):
                    if line:
                        logger.info(f"  {line}")

            except subprocess.CalledProcessError as e:
                logger.error(f"✗ Failed to generate plots for {json_file}: {e}")
                logger.error(f"Plot script stdout: {e.stdout}")
                logger.error(f"Plot script stderr: {e.stderr}")
                success = False
            except Exception as e:
                logger.error(f"✗ Error running plot generation for {json_file}: {e}")
                success = False

        if success:
            logger.info("✓ All VMAF plots generated successfully")
        else:
            logger.warning("⚠️ Some plot generation failed")

        return success

    def process(self):
        """Main processing function."""
        logger.info("🎬 Starting video sync and VMAF analysis")
        start_time = datetime.now()

        # Step 1: Find sync point in distorted video
        logger.info("📊 Step 1: Finding sync point")
        sync_timestamp = self.find_sync_point(self.distorted_path)

        if sync_timestamp is None:
            logger.error("✗ Could not determine sync point")
            return False

        logger.info(f"✓ Sync point determined: {sync_timestamp:.3f}s")

        # Step 2: Trim the distorted video
        logger.info("✂️ Step 2: Trimming distorted video")
        if not self.trim_video(sync_timestamp):
            logger.error("✗ Failed to trim video")
            return False

        # Step 4: Get first frame number from trimmed video and save as PNG
        logger.info("🔍 Step 4: Getting first frame number from trimmed video")
        first_frame_number = self.get_first_frame_number()

        # Step 5: Get frame number from trimmed video
        logger.info("📖 Step 5: Reading frame number from trimmed video")
        if first_frame_number is not None:
            logger.info(f"✓ Frame number from trimmed video: {first_frame_number}")

            # Step 6: Find that frame in original video
            logger.info(f"🔍 Step 6: Finding frame {first_frame_number} in original video")
            found_frame_position = self.find_frame_in_original_video(first_frame_number)

            if found_frame_position is not None:
                # Convert frame position to timestamp (assuming 30fps)
                vmaf_offset = found_frame_position / 30.0
                logger.info(f"✓ Found frame {first_frame_number} at frame position {found_frame_position}")
                logger.info(f"✓ Converting to timestamp: {vmaf_offset:.6f}s for VMAF analysis")

                # Save the found frame from reference video
                self.save_reference_frame_at_position(found_frame_position, first_frame_number)
            else:
                logger.warning("Could not find frame in original video, using 0")
                vmaf_offset = 0
        else:
            logger.warning("No frame number detected, using 0")
            vmaf_offset = 0


        # Step 7: Run VMAF analysis
        logger.info("📈 Step 7: Running VMAF analysis")
        if not self.run_vmaf_analysis(vmaf_offset):
            logger.error("✗ Failed to run VMAF analysis")
            return False

        # Step 8: Copy distorted file to results directory
        logger.info("📄 Step 8: Copying distorted file to results directory")
        if not self.copy_distorted_file():
            logger.warning("⚠️ Failed to copy distorted file (continuing anyway)")

        # Step 9: Generate VMAF plots
        logger.info("📊 Step 9: Generating VMAF plots")
        if not self.generate_vmaf_plots():
            logger.warning("⚠️ Failed to generate VMAF plots (continuing anyway)")

        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        logger.info("🎉 Process completed successfully!")
        logger.info(f"⏱️ Total processing time: {duration.total_seconds():.1f} seconds")
        logger.info(f"📁 Results directory: {self.results_dir}")
        logger.info(f"📄 Results logged to: {self.results_log}")
        logger.info(f"🎥 Trimmed video: {self.trimmed_path}")

        return True

def main():
    parser = argparse.ArgumentParser(description='Video sync detection and VMAF scoring')
    parser.add_argument('reference', help='Reference video file (source)')
    parser.add_argument('distorted', help='Distorted video file (test)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--buffer', type=float, default=5.0,
                       help='Buffer time in seconds after sync point (default: 5.0)')
    parser.add_argument('--seek-distorted', type=float, default=0.0,
                       help='Skip this many seconds when looking for numbered frames in distorted video (default: 0.0)')

    args = parser.parse_args()

    try:
        processor = VideoSyncVMAF(args.reference, args.distorted, args.buffer, args.seek_distorted)
        # Apply debug setting after logger is configured
        if args.debug:
            setup_logging(processor.results_log, debug=True)
        success = processor.process()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
