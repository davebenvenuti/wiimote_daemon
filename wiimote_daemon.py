#!/usr/bin/python

#
# Starts wminput in daemon mode, and monitors for wiimote inactivity.  if a timeout is reached, the wiimote will be disconnected/powered down
# @author dbenvenuti
#

# configurable constants
WIIMOTE_ADDY='00:19:1D:63:EE:BB'
TIMEOUT=7 * 60 # 7 minutes, in seconds
LOG_FILENAME = '/var/log/wiimote_daemon'

# other constants
WMINPUT = '/usr/bin/wminput'
WMINPUT_ARGS = ['-c', 'xbmc', '-d', WIIMOTE_ADDY]
#############################

import os, threading, time, sys, signal, logging

# start the logger
logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)

g_bytes_read = 0  # byte count read from event driver, used to determine whether there was activity
g_lock = threading.Lock()

class EventReaderThread (threading.Thread):

    def __init__(self,event_driver):
        threading.Thread.__init__(self)
        self.event_driver = event_driver

    def run(self):
        logging.info("howdy from the event driver reader thread")

        wfp = open(self.event_driver, 'r')
        
        global g_lock
        global g_bytes_read

        while True:
            try:
                wfp.read(1)

                g_lock.acquire()
                g_bytes_read += 1
                g_lock.release()

            except Exception as inst:
                logging.error("error reading %s, %s" % (self.event_driver,inst))
                break

        logging.warning("exiting event driver reader thread...")
        wfp.close()
        sys.exit(-1)
############################

child_pid = 0

def wiimote_disconnect():
    os.system('hcitool dc %s' % WIIMOTE_ADDY)

def handle_signal(signal, frame):
    global child_pid
    os.kill(child_pid, signal.SIGKILL)
############################

event_drivers = set()
# figure out which event driver we're using. take a snapshot of /dev/input
for dirname, dirnames, filenames in os.walk('/dev/input'):
    for filename in filenames:
        if filename.startswith('event'):
            event_drivers.add(filename)

#logging.info "before: found %d total event drivers" % (len(event_drivers),)

child_pid = os.fork()


##### child process
if child_pid == 0:
    logging.info("starting %s" % (WMINPUT,))
    os.execvp(WMINPUT, (WMINPUT,) + tuple(WMINPUT_ARGS))
    # never returns




##### parent process
event_driver = None
wminput_timeout = 2
logging.info("waiting %d seconds for wminput..." % (wminput_timeout,))
time.sleep(wminput_timeout)
# figure out which event driver wminput created
for dirname, dirnames, filenames in os.walk('/dev/input'):
    for filename in filenames:
        if filename.startswith('event') and filename not in event_drivers:
            # we got it
            event_driver = '/dev/input/%s' % (filename,)

if event_driver == None:
    logging.error("error could not detect wiimote event driver, quitting")
    os.kill(child_pid,signal.SIGTERM)
    sys.exit(-1)

logging.info("found event driver %s, starting up..." % (event_driver,))

# launch the reader thread
t = EventReaderThread(event_driver)
t.start()

logging.info("wiimote timeout set to %d seconds.  monitoring..." % (TIMEOUT,))

# infinite loop.  sleep for 10 minutes, if no wiimote activity, disconnect the wiimote

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

try:
    while True:
        cur_bytes_read = g_bytes_read

        time.sleep(TIMEOUT)
        g_lock.acquire()
        #logging.info "waking up. g_bytes_read = %d; cur_bytes_read = %d" % (g_bytes_read,cur_bytes_read)
        if g_bytes_read > 0 and cur_bytes_read == g_bytes_read:
            logging.info("no wiimote activity for %d seconds.  disconnecting wiimote..." % (TIMEOUT,))
            wiimote_disconnect()
            g_bytes_read = 0
            cur_bytes_read = 0
    
        g_lock.release()

except Exception as e:
    logging.error("exception: %s" % (e,))

