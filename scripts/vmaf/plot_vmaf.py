#!/usr/bin/env python3
"""Plot VMAF analysis results from JSON files.

Loads VMAF JSON output files and generates visualization plots including histogram
distributions by quality categories and frame-by-frame score plots.
"""
import json
import sys
import os
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def load_vmaf_json(json_path):
    """Load VMAF JSON file and extract frame scores and overall statistics"""
    with open(json_path, 'r') as f:
        data = json.load(f)

    frames = data['frames']
    scores = []
    frame_numbers = []

    for frame in frames:
        if 'metrics' in frame and 'vmaf' in frame['metrics']:
            scores.append(frame['metrics']['vmaf'])
            frame_numbers.append(frame['frameNum'])

    # Extract overall VMAF statistics if available
    vmaf_stats = None
    if 'pooled_metrics' in data and 'vmaf' in data['pooled_metrics']:
        vmaf_stats = data['pooled_metrics']['vmaf']

    return scores, frame_numbers, vmaf_stats

def get_quality_bucket(score):
    """Categorize VMAF score into quality buckets"""
    if score >= 90:
        return "Excellent (90+)"
    elif score >= 74:
        return "Good (74-90)"
    elif score >= 58:
        return "Fair (58-74)"
    elif score >= 38:
        return "Poor (38-58)"
    else:
        return "Bad (<38)"

def plot_histogram(scores, output_path, csv_path, vmaf_stats=None):
    """Create histogram of VMAF scores by quality buckets and save CSV for sheets"""
    buckets = {
        "Excellent (90+)": 0,
        "Good (74-90)": 0,
        "Fair (58-74)": 0,
        "Poor (38-58)": 0,
        "Bad (<38)": 0
    }

    for score in scores:
        bucket = get_quality_bucket(score)
        buckets[bucket] += 1

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ['#2ecc71', '#3498db', '#f39c12', '#e74c3c', '#c0392b']
    bars = ax.bar(buckets.keys(), buckets.values(), color=colors)

    ax.set_xlabel('Quality Category', fontsize=12)
    ax.set_ylabel('Number of Frames', fontsize=12)
    ax.set_title('VMAF Score Distribution by Quality Category', fontsize=14, fontweight='bold')

    # Add value labels on bars
    for bar, value in zip(bars, buckets.values()):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{value:,}', ha='center', va='bottom', fontsize=10)

    # Add percentage labels
    total_frames = sum(buckets.values())
    for bar, value in zip(bars, buckets.values()):
        height = bar.get_height()
        percentage = (value / total_frames) * 100 if total_frames > 0 else 0
        ax.text(bar.get_x() + bar.get_width()/2., height/2,
                f'{percentage:.1f}%', ha='center', va='center',
                fontsize=9, color='white', fontweight='bold')

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Histogram saved: {output_path}")

    # Create CSV file for Google Sheets
    with open(csv_path, 'w') as f:
        # Get statistics from JSON or calculate from scores
        if vmaf_stats:
            min_score = vmaf_stats.get('min', np.min(scores))
            max_score = vmaf_stats.get('max', np.max(scores))
            mean_score = vmaf_stats.get('mean', np.mean(scores))
            harmonic_mean_score = vmaf_stats.get('harmonic_mean', 0)
        else:
            min_score = np.min(scores)
            max_score = np.max(scores)
            mean_score = np.mean(scores)
            harmonic_mean_score = len(scores) / np.sum(1.0 / np.array(scores)) if all(s > 0 for s in scores) else 0

        # Write header row with statistics and ranges
        f.write("Min\tMax\tMean\tHarmonic Mean\tBad (<38)\tPoor (38-58)\tFair (58-74)\tGood (74-90)\tExcellent (90+)\tTotal Frames\n")

        # Write percentage values and total frames
        percentages = []
        for bucket_name in ["Bad (<38)", "Poor (38-58)", "Fair (58-74)", "Good (74-90)", "Excellent (90+)"]:
            value = buckets[bucket_name]
            percentage = (value / total_frames) * 100 if total_frames > 0 else 0
            percentages.append(f"{percentage:.1f}%")

        # Join statistics, percentages with tabs and add total frames
        f.write(f"{min_score}\t{max_score}\t{mean_score}\t{harmonic_mean_score}\t" + "\t".join(percentages) + f"\t{total_frames}\n")

    print(f"CSV for Google Sheets saved: {csv_path}")


def plot_frame_numbers(scores, frame_numbers, output_path):
    """Create plot with frame numbers on x-axis and VMAF score on y-axis"""
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.plot(frame_numbers, scores, linewidth=1, color='#9b59b6', alpha=0.8)

    # Add quality threshold lines
    ax.axhline(y=90, color='#2ecc71', linestyle='--', alpha=0.5, label='Excellent (90+)')
    ax.axhline(y=74, color='#3498db', linestyle='--', alpha=0.5, label='Good (74+)')
    ax.axhline(y=58, color='#f39c12', linestyle='--', alpha=0.5, label='Fair (58+)')
    ax.axhline(y=38, color='#e74c3c', linestyle='--', alpha=0.5, label='Poor (38+)')

    ax.set_xlabel('Frame Number', fontsize=12)
    ax.set_ylabel('VMAF Score', fontsize=12)
    ax.set_title('VMAF Score by Frame Number', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.grid(True, alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)

    # Add statistics
    avg_score = np.mean(scores)
    min_score = np.min(scores)
    max_score = np.max(scores)
    stats_text = f'Avg: {avg_score:.1f} | Min: {min_score:.1f} | Max: {max_score:.1f}'
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Frame number plot saved: {output_path}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python plot_vmaf.py <vmaf_json_file>")
        sys.exit(1)

    json_path = Path(sys.argv[1])

    if not json_path.exists():
        print(f"Error: File {json_path} not found")
        sys.exit(1)

    print(f"Loading VMAF data from: {json_path}")

    try:
        scores, frame_numbers, vmaf_stats = load_vmaf_json(json_path)

        if not scores:
            print("Error: No VMAF scores found in the JSON file")
            sys.exit(1)

        print(f"Loaded {len(scores)} frames")

        # Generate output filenames in the same directory as the JSON
        output_dir = json_path.parent
        base_name = json_path.stem

        histogram_path = output_dir / f"{base_name}_histogram.png"
        frame_plot_path = output_dir / f"{base_name}_frames.png"
        csv_path = output_dir / f"{base_name}_histogram.tsv"

        # Create plots
        plot_histogram(scores, histogram_path, csv_path, vmaf_stats)
        plot_frame_numbers(scores, frame_numbers, frame_plot_path)

        print(f"\nAll plots generated successfully in: {output_dir}")
        print(f"Average VMAF score: {np.mean(scores):.2f}")

    except Exception as e:
        print(f"Error processing VMAF data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
