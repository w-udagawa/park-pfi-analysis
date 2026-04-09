"""Park-PFI Potential Analysis Pipeline CLI."""

import argparse
import os
import sys
import time
from typing import Any, Callable, Dict, Optional, Union

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from src.config_loader import load_config
from src.data_collector import collect_all_data
from src.data_validator import validate_data_coverage
from src.pedestrian_flow import calculate_all_flow_scores
from src.surrounding_analysis import analyze_all_surroundings
from src.vibrancy_evaluator import evaluate_all_parks, BADGE_KEYS, BADGE_LABELS
from src.report_generator import generate_excel, generate_markdown


ProgressCallback = Callable[[str, float], None]


def run_pipeline(
    config_or_path: Union[str, Dict[str, Any]],
    output_dir: str = None,
    skip_api: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
):
    """Execute the full analysis pipeline.

    Args:
        config_or_path: YAML ファイルパス (str) または config dict
        output_dir: レポート出力先ディレクトリ
        skip_api: (未使用、互換性のため残置)
        progress_callback: (step_name, ratio_0_1) を受け取る進捗通知関数
    """
    start_time = time.time()

    def report(step: str, ratio: float):
        if progress_callback:
            progress_callback(step, ratio)

    print("=" * 60)
    print("Park-PFI Potential Analysis")
    print("=" * 60)

    # Step 1: Load config
    print("\n[1/6] Loading configuration...")
    report("設定読み込み", 0.02)
    if isinstance(config_or_path, dict):
        config = config_or_path
    else:
        config = load_config(config_or_path)
    municipality = config["municipality"]["name"]
    print(f"  Municipality: {municipality}")
    print(f"  Min area: {config['min_area']}m²")

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output")

    # Step 2: Collect data
    print(f"\n[2/6] Collecting data...")
    report("データ収集 (MLIT DPF / Overpass)", 0.10)
    data = collect_all_data(config)
    parks = data["parks"]
    stations = data["stations"]
    facilities = data["facilities"]
    print(f"  Parks: {len(parks)}")
    print(f"  Stations: {len(stations)}")
    for cat, items in facilities.items():
        print(f"  Facilities [{cat}]: {len(items)}")

    # Step 3: Data validation
    validation = None
    if config["report"].get("enable_data_validation", True):
        print(f"\n[3/6] Running data coverage diagnostics...")
        report("データ品質チェック", 0.40)
        validation = validate_data_coverage(config, parks, stations, facilities)
        print(f"  Status: {validation['summary']} (score: {validation['overall_score']})")
        for issue in validation.get("issues", []):
            print(f"  [{issue['severity']}] {issue['category']}: {issue['message']}")

    # Step 4: Pedestrian flow analysis
    print(f"\n[4/6] Calculating pedestrian flow scores...")
    report("歩行者流量分析", 0.55)
    flow_all = calculate_all_flow_scores(parks, stations, config)
    # Show top 5 flow parks
    top_flow = sorted(flow_all.items(), key=lambda x: -x[1]["normalized_score"])[:5]
    for name, data in top_flow:
        print(f"  {name}: {data['normalized_score']} (raw: {data['raw_score']}, stations: {data['station_count']})")

    # Step 5: Surrounding facility analysis
    print(f"\n[5/6] Analyzing surrounding facilities...")
    report("周辺施設分析", 0.70)
    surroundings_all = analyze_all_surroundings(parks, facilities, config)

    # Step 6: Vibrancy evaluation & report generation
    print(f"\n[6/6] Evaluating vibrancy potential and generating reports...")
    report("にぎわい評価", 0.85)
    scored_parks = evaluate_all_parks(parks, surroundings_all, flow_all, config)

    # Show rank distribution (にぎわいスコアベース)
    rank_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
    for p in scored_parks:
        rank_dist[p["vibrancy"]["rank"]] += 1
    print(f"  にぎわいランク分布: " + ", ".join(f"{r}={c}" for r, c in rank_dist.items()))

    # Show badge distribution
    badge_dist = {k: 0 for k in BADGE_KEYS}
    for p in scored_parks:
        for k in BADGE_KEYS:
            if p["badges"].get(k):
                badge_dist[k] += 1
    print(f"  バッジ分布: " + ", ".join(f"{BADGE_LABELS[k]}={v}" for k, v in badge_dist.items()))

    # Generate reports
    report("Excel/Markdown 生成", 0.95)
    excel_path = generate_excel(scored_parks, config, output_dir, validation=validation)
    md_path = generate_markdown(scored_parks, config, output_dir, validation=validation)
    report("完了", 1.0)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Analysis complete! ({elapsed:.1f}s)")
    print(f"  Excel: {excel_path}")
    print(f"  Markdown: {md_path}")
    print(f"  Total parks analyzed: {len(scored_parks)}")
    top = scored_parks[0]
    print(f"  Top park: {top['name']} (にぎわいスコア: {top['vibrancy']['score']}, Rank: {top['vibrancy']['rank']})")
    print(f"{'=' * 60}")

    return scored_parks, excel_path, md_path


def main():
    parser = argparse.ArgumentParser(
        description="Park-PFI Potential Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --config config/setagaya.yaml
  python main.py --config config/setagaya.yaml --output ./results
        """,
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to municipality YAML config file",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory (default: ./output)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config file not found: {args.config}")
        sys.exit(1)

    run_pipeline(args.config, args.output)


if __name__ == "__main__":
    main()
