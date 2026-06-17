#!/usr/bin/env python3
"""
batch_runner.py -- Sequentially run the AI news video generation pipeline
to batch-produce and upload multiple videos across different categories 
using proportional interleaving (e.g., 7:3 ratio).
"""

import argparse
import subprocess
import sys
import os
import time

def generate_run_sequence(categories: list[str], ratio_str: str, count: int) -> list[str]:
    """
    Proportionally interleave categories based on a ratio string (e.g., '7:3').
    Ensures runs are spread as evenly as possible.
    """
    try:
        ratio_parts = [float(x) for x in ratio_str.split(':')]
    except Exception:
        ratio_parts = [1.0] * len(categories)

    if len(ratio_parts) != len(categories):
        ratio_parts = [1.0] * len(categories)

    total_ratio = sum(ratio_parts)
    if total_ratio <= 0:
        ratio_parts = [1.0] * len(categories)
        total_ratio = sum(ratio_parts)

    percentages = [p / total_ratio for p in ratio_parts]

    # Compute target counts for each category
    counts = [int(round(pct * count)) for pct in percentages]

    # Adjust counts so they sum exactly to the requested count
    while sum(counts) < count:
        diffs = [pct * count - counts[idx] for idx, pct in enumerate(percentages)]
        best_idx = diffs.index(max(diffs))
        counts[best_idx] += 1
    while sum(counts) > count:
        diffs = [counts[idx] - pct * count for idx, pct in enumerate(percentages)]
        best_idx = diffs.index(max(diffs))
        counts[best_idx] -= 1

    # Proportionally interleave the categories
    run_list = []
    temp_counts = list(counts)
    acc = [0.0] * len(categories)
    steps = [1.0 / pct if pct > 0 else float('inf') for pct in percentages]

    for _ in range(count):
        candidates = []
        for idx in range(len(categories)):
            if temp_counts[idx] > 0:
                due = acc[idx] + steps[idx]
                candidates.append((due, idx))
        if not candidates:
            break
        
        # Sort by next due step to spread occurrences evenly
        candidates.sort(key=lambda x: x[0])
        chosen_idx = candidates[0][1]

        run_list.append(categories[chosen_idx])
        temp_counts[chosen_idx] -= 1
        acc[chosen_idx] += steps[chosen_idx]

    return run_list


def main():
    parser = argparse.ArgumentParser(description="AI News Video Batch Runner")
    parser.add_argument("--count", type=int, default=10, help="Number of videos to generate in this batch")
    parser.add_argument("--channel", choices=["newscup", "newscup_india"], default="newscup", help="YouTube channel key")
    parser.add_argument("--categories", default="general", help="Comma-separated categories (e.g. general)")
    parser.add_argument("--ratio", default="", help="Colon-separated ratio (e.g. 1). Defaults to 1 for each category.")
    parser.add_argument("--format", choices=["short", "long", "both"], default="short", help="Video format")
    parser.add_argument("--upload-spacing", type=int, help="Upload spacing between videos in minutes")
    parser.add_argument("--upload-jitter-min", type=int, help="Minimum upload scheduling jitter in minutes")
    parser.add_argument("--upload-jitter-max", type=int, help="Maximum upload scheduling jitter in minutes")
    args, unknown = parser.parse_known_args()

    categories_list = [c.strip() for c in args.categories.split(",") if c.strip()]
    
    # Default ratio setups
    ratio_str = args.ratio
    if not ratio_str:
        ratio_str = ":".join(["1"] * len(categories_list))

    run_sequence = generate_run_sequence(categories_list, ratio_str, args.count)

    print("=" * 60)
    print(f"Starting batch runner: Generating {args.count} videos sequentially.")
    print(f"Channel: {args.channel} | Categories: {categories_list} (Ratio: {ratio_str})")
    print(f"Plan: {run_sequence}")
    print("=" * 60)

    # Force AUTO_UPLOAD to always be 'true' for batch runs
    os.environ["AUTO_UPLOAD"] = "true"

    python_exe = sys.executable
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

    success_count = 0
    for i, category in enumerate(run_sequence, 1):
        print(f"\n[Batch Runner] Video {i}/{args.count} | Category: '{category}' starting...")
        
        cmd = [
            python_exe,
            script_path,
            "--channel", args.channel,
            "--category", category,
            "--format", args.format
        ]
        if args.upload_spacing is not None:
            cmd.extend(["--upload-spacing", str(args.upload_spacing)])
        if args.upload_jitter_min is not None:
            cmd.extend(["--upload-jitter-min", str(args.upload_jitter_min)])
        if args.upload_jitter_max is not None:
            cmd.extend(["--upload-jitter-max", str(args.upload_jitter_max)])
        cmd.extend(unknown)
        
        start_time = time.time()
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            
            for line in process.stdout:
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    enc = sys.stdout.encoding or "utf-8"
                    sys.stdout.write(line.encode(enc, errors="replace").decode(enc))
                    sys.stdout.flush()
                
            process.wait()
            duration = time.time() - start_time
            
            if process.returncode == 0:
                print(f"[Batch Runner] Run {i}/{args.count} ({category}) succeeded in {duration:.1f}s.")
                success_count += 1
            else:
                print(f"[Batch Runner] Run {i}/{args.count} ({category}) failed with exit code {process.returncode} in {duration:.1f}s.")
                
        except Exception as e:
            print(f"[Batch Runner] Error during run {i} ({category}): {e}")
            
        if i < args.count:
            print("[Batch Runner] Waiting 5 seconds before starting next run...")
            time.sleep(5)

    print("\n" + "=" * 60)
    print(f"Batch generation completed: {success_count}/{args.count} runs succeeded.")
    print("=" * 60)

if __name__ == "__main__":
    main()
