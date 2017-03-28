'''
Created on Mar 27, 2017

@author: andrew
'''
import signal
import sys
import time

def sigterm_handler(_signum, _frame):
    print("Python beAnnoying caught SIGTERM, sleeping for 15!")
    time.sleep(15)
    sys.exit(0)
    
if __name__ == '__main__':
    signal.signal(signal.SIGTERM, sigterm_handler)
    while True:
        time.sleep(1)