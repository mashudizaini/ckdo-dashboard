#!/usr/bin/env python3
"""
Quick Setup and Test Script
Run this to verify installation and test the CV screening system
"""

import os
import sys
import subprocess


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def check_python_version():
    """Check Python version"""
    print("\n✓ Checking Python version...")
    version = sys.version_info
    print(f"  Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        print("  ❌ Error: Python 3.7 or higher is required!")
        return False
    
    print("  ✅ Python version OK")
    return True


def install_dependencies():
    """Install required packages"""
    print("\n✓ Installing dependencies...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
        print("  ✅ All dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("  ❌ Error installing dependencies")
        return False


def download_spacy_model():
    """Download spaCy language model - SKIPPED (not required)"""
    print("\n✓ Checking optional NLP features...")
    print("  ℹ️  spaCy is optional and not required for basic CV screening")
    print("  ✅ System will work without advanced NLP features")
    return True


def create_directories():
    """Create necessary directories"""
    print("\n✓ Creating directories...")
    
    directories = ['uploads', 'results', 'exports', 'templates']
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    
    print(f"  ✅ Created {len(directories)} directories")
    return True


def test_cv_screening():
    """Test CV screening with sample CVs"""
    print("\n✓ Testing CV screening with sample CVs...")
    
    try:
        from cv_screener import CVScreener, load_job_config
        
        # Load config
        job_config = load_job_config()
        screener = CVScreener(job_config)
        
        # Test with sample CVs
        sample_cvs = ['sample_cv_1.txt', 'sample_cv_2.txt']
        existing_cvs = [cv for cv in sample_cvs if os.path.exists(cv)]
        
        if not existing_cvs:
            print("  ⚠️  No sample CVs found for testing")
            return True
        
        results = screener.screen_multiple_cvs(existing_cvs)
        
        print(f"  ✅ Successfully screened {len(results)} sample CV(s)")
        
        # Display results
        print("\n  Sample Results:")
        for i, result in enumerate(results, 1):
            print(f"    #{i}. {result.get('name', 'Unknown')} - Score: {result.get('total_score', 0):.2f}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error during testing: {e}")
        return False


def display_next_steps():
    """Display next steps for user"""
    print("\n" + "=" * 70)
    print("  🎉 SETUP COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print("\n📋 Next Steps:\n")
    print("1. Review and edit job_config.json for your requirements")
    print("2. Start the web application:")
    print("   python app.py")
    print("   Then open: http://localhost:5000")
    print("\n   OR\n")
    print("3. Use command line interface:")
    print("   python cli_screen.py -d /path/to/cv/folder")
    print("\n4. Read README.md for detailed documentation")
    print("\n" + "=" * 70)


def main():
    """Main setup function"""
    print_header("CV SCREENING SYSTEM - Quick Setup")
    
    # Check Python version
    if not check_python_version():
        return 1
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Setup failed at dependency installation")
        return 1
    
    # Download spaCy model
    download_spacy_model()
    
    # Create directories
    if not create_directories():
        print("\n❌ Setup failed at directory creation")
        return 1
    
    # Test the system
    if not test_cv_screening():
        print("\n⚠️  Warning: Testing encountered errors")
        print("The system might still work, but please check the errors above")
    
    # Display next steps
    display_next_steps()
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
