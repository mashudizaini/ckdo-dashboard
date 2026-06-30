#!/usr/bin/env python3
"""
CV Screening - Command Line Interface
Standalone script for batch processing CVs without web interface
"""

import os
import sys
import json
import argparse
import pandas as pd
from datetime import datetime
from cv_screener import CVScreener, load_job_config


def print_banner():
    """Print application banner"""
    print("=" * 70)
    print("           CV SCREENING SYSTEM - Command Line Interface")
    print("              AI-Powered Recruitment for CKD Otto Pharma")
    print("=" * 70)
    print()


def scan_cv_directory(directory):
    """Scan directory for CV files"""
    supported_extensions = ['.pdf', '.docx', '.doc', '.txt']
    cv_files = []
    
    if not os.path.exists(directory):
        print(f"❌ Error: Directory '{directory}' not found!")
        return []
    
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            ext = os.path.splitext(filename)[1].lower()
            if ext in supported_extensions:
                cv_files.append(file_path)
    
    return cv_files


def display_config(config):
    """Display job configuration"""
    print("📋 Job Configuration:")
    print("-" * 70)
    print(f"Position: {config['position_title']}")
    print(f"Required Skills: {', '.join(config['required_skills'])}")
    print(f"Minimum Experience: {config['min_experience']} years")
    print(f"Education Keywords: {len(config['education_keywords'])} keywords")
    print(f"Certification Keywords: {len(config.get('certification_keywords', []))} keywords")
    print("-" * 70)
    print()


def display_results_summary(results):
    """Display screening results summary"""
    print("\n" + "=" * 70)
    print("                    SCREENING RESULTS SUMMARY")
    print("=" * 70)
    
    total = len(results)
    highly_recommended = sum(1 for r in results if r.get('recommendation') == 'Highly Recommended')
    recommended = sum(1 for r in results if r.get('recommendation') == 'Recommended')
    consider = sum(1 for r in results if r.get('recommendation') == 'Consider')
    not_recommended = sum(1 for r in results if r.get('recommendation') == 'Not Recommended')
    
    scores = [r.get('total_score', 0) for r in results if 'total_score' in r]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    print(f"\n📊 Statistics:")
    print(f"   Total CVs Processed: {total}")
    print(f"   ✅ Highly Recommended: {highly_recommended}")
    print(f"   👍 Recommended: {recommended}")
    print(f"   🤔 Consider: {consider}")
    print(f"   ❌ Not Recommended: {not_recommended}")
    print(f"   📈 Average Score: {avg_score:.2f}")
    if scores:
        print(f"   🏆 Highest Score: {max(scores):.2f}")
        print(f"   📉 Lowest Score: {min(scores):.2f}")
    
    print("\n" + "=" * 70)


def display_top_candidates(results, top_n=10):
    """Display top N candidates"""
    print(f"\n🏆 Top {top_n} Candidates:")
    print("-" * 70)
    
    for i, result in enumerate(results[:top_n], 1):
        print(f"\n#{i}. {result.get('name', 'Unknown')}")
        print(f"   Score: {result.get('total_score', 0):.2f} | {result.get('recommendation', 'N/A')}")
        print(f"   Experience: {result.get('experience_years', 0)} years")
        print(f"   Skills: {result.get('skills_matched', 'N/A')}")
        print(f"   Email: {result.get('email', 'N/A')}")
        print(f"   Phone: {result.get('phone', 'N/A')}")
        print(f"   File: {result.get('filename', 'N/A')}")
    
    print("-" * 70)


def export_results(results, output_format='excel', output_file=None):
    """Export results to file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create exports directory if not exists
    os.makedirs('exports', exist_ok=True)
    
    if output_format == 'excel':
        if not output_file:
            output_file = f"exports/cv_screening_results_{timestamp}.xlsx"
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        # Select columns
        columns = [
            'name', 'email', 'phone', 'total_score', 'recommendation',
            'experience_years', 'skills_matched', 'education',
            'skills_score', 'experience_score', 'education_score', 'certification_score',
            'filename', 'processed_date'
        ]
        
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]
        
        # Export
        df.to_excel(output_file, index=False, sheet_name='Screening Results')
        print(f"\n✅ Results exported to Excel: {output_file}")
        
    elif output_format == 'json':
        if not output_file:
            output_file = f"exports/cv_screening_results_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Results exported to JSON: {output_file}")
    
    elif output_format == 'csv':
        if not output_file:
            output_file = f"exports/cv_screening_results_{timestamp}.csv"
        
        df = pd.DataFrame(results)
        columns = [
            'name', 'email', 'phone', 'total_score', 'recommendation',
            'experience_years', 'skills_matched', 'education', 'filename'
        ]
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]
        
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n✅ Results exported to CSV: {output_file}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='CV Screening System - Batch Processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen all CVs in a directory
  python cli_screen.py -d ./cv_folder
  
  # Use custom config and export to Excel
  python cli_screen.py -d ./cv_folder -c custom_config.json -e excel
  
  # Show top 20 candidates and export to CSV
  python cli_screen.py -d ./cv_folder -t 20 -e csv
        """
    )
    
    parser.add_argument('-d', '--directory', 
                        required=True,
                        help='Directory containing CV files')
    
    parser.add_argument('-c', '--config',
                        default='job_config.json',
                        help='Job configuration file (default: job_config.json)')
    
    parser.add_argument('-e', '--export',
                        choices=['excel', 'json', 'csv', 'none'],
                        default='excel',
                        help='Export format (default: excel)')
    
    parser.add_argument('-o', '--output',
                        help='Output file path (optional)')
    
    parser.add_argument('-t', '--top',
                        type=int,
                        default=10,
                        help='Number of top candidates to display (default: 10)')
    
    parser.add_argument('--no-display',
                        action='store_true',
                        help='Skip displaying results (only export)')
    
    args = parser.parse_args()
    
    # Print banner
    print_banner()
    
    # Load configuration
    print("📝 Loading job configuration...")
    try:
        job_config = load_job_config(args.config)
        display_config(job_config)
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return 1
    
    # Scan directory for CVs
    print(f"🔍 Scanning directory: {args.directory}")
    cv_files = scan_cv_directory(args.directory)
    
    if not cv_files:
        print(f"❌ No CV files found in '{args.directory}'")
        print("   Supported formats: PDF, DOCX, DOC, TXT")
        return 1
    
    print(f"✅ Found {len(cv_files)} CV file(s)")
    print()
    
    # Initialize screener
    print("🚀 Starting CV screening process...")
    print("-" * 70)
    screener = CVScreener(job_config)
    
    # Screen CVs
    results = screener.screen_multiple_cvs(cv_files)
    
    print("\n✅ Screening completed!")
    
    # Display results
    if not args.no_display:
        display_results_summary(results)
        display_top_candidates(results, args.top)
    
    # Export results
    if args.export != 'none':
        export_results(results, args.export, args.output)
    
    print("\n" + "=" * 70)
    print("                    Process Completed Successfully!")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
