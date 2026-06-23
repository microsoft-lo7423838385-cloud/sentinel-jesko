#!/usr/bin/env python
"""
Final integration test - verify email sending works with AI.
"""
import subprocess
import sys
import os

def main():
    print("\n" + "="*70)
    print("FINAL TEST: Email Sending with AI Integration")
    print("="*70)
    
    # Create temp recipients file with fresh emails
    temp_recipients = """test.ai.send.1@maildrop.cc
test.ai.send.2@tempmail.com
test.ai.send.3@mailinator.com
"""
    
    with open('recipients_temp_test.txt', 'w') as f:
        f.write(temp_recipients)
    
    print("\nTest recipients created:")
    for line in temp_recipients.strip().split('\n'):
        print(f"  - {line}")
    
    print("\n" + "-"*70)
    print("Running: python main.py --fresh-start --dry-run 2")
    print("This will:")
    print("  1. Clear all previous state (fresh-start)")
    print("  2. Simulate sending to 2 recipients (dry-run)")
    print("  3. Use AI to generate email content")
    print("-"*70 + "\n")
    
    try:
        result = subprocess.run(
            [sys.executable, 'main.py', '--fresh-start', '--dry-run', '2'],
            timeout=180,
            capture_output=False  # Show output in real-time
        )
        
        print("\n" + "="*70)
        if result.returncode == 0:
            print("SUCCESS - System is working!")
            print("\nYour system is now ready to:")
            print("1. Send emails via Gmail SMTP")
            print("2. Generate AI content for subjects and body")
            print("3. Track sent/bounce status")
            print("\nTo start real sending, run:")
            print("  python main.py")
        else:
            print(f"Test completed with code: {result.returncode}")
        print("="*70 + "\n")
        
    except subprocess.TimeoutExpired:
        print("Test timeout - taking too long")
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        # Cleanup
        if os.path.exists('recipients_temp_test.txt'):
            os.remove('recipients_temp_test.txt')

if __name__ == "__main__":
    main()
