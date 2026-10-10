"""Legacy simulation validator: isolated mocks only, never live SMS.

The 60% simulation is not a forecast and must never reach a real provider.
Run the maintained worker safety tests instead; all SMS/GitHub calls are mocked.
"""
import subprocess
import sys
from pathlib import Path


def main():
    print('SIMULATION SAFETY CHECK: mocked tests only; no SMS or weather warning.')
    return subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
         '-p', 'test_scheduled_sms_worker.py', '-v'],
        cwd=Path(__file__).resolve().parent, check=False,
    ).returncode


if __name__ == '__main__':
    raise SystemExit(main())
