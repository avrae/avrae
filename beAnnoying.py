'''
Created on Mar 27, 2017

@author: andrew
'''
import signal
import sys
import time

def sigterm_handler(_signum, _frame):
    print("Sleeping for 20 seconds before exit...")
    time.sleep(20)
    sys.exit(0)
    
if __name__ == '__main__':
    signal.signal(signal.SIGTERM, sigterm_handler)
    while True:
        time.sleep(20)