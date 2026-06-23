#!/usr/bin/env python
"""
Test sending an email with AI content generation.
Uses --dry-run to simulate without actually sending.
"""
import subprocess
import sys
import os

def test_dry_run_send():
    """Test dry-run send with AI enabled."""
    
    print("\n" + "="*70)
    print("TESTING EMAIL SEND WITH AI (DRY-RUN)")
    print("="*70)
    print("\nRunning: python main.py --dry-run 1")
    print("This will simulate sending 1 email with AI-generated content\n")
    
    try:
        # Run main.py with --dry-run to test sending without actually sending
        result = subprocess.run(
            [sys.executable, 'main.py', '--dry-run', '1'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=False,
            timeout=300
        )
        
        print("\n" + "="*70)
        if result.returncode == 0:
            print("✓ TEST PASSED - Dry-run completed successfully")
            print("\nNext steps:")
            print("1. Review the output above to verify AI content generation worked")
            print("2. If AI content was generated, you can safely run:")
            print("   python main.py")
            print("   to start actual email sending")
        else:
            print("❌ TEST FAILED - Dry-run encountered an error")
            print(f"Exit code: {result.returncode}")
        print("="*70 + "\n")
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ TEST TIMEOUT - Dry-run took too long")
        return False
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_dry_run_send()
    sys.exit(0 if success else 1)
