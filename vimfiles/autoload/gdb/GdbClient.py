# Echo client program
import socket
import sys
from sockutils import *

def get_reply(input):
    HOST = '127.0.0.1'                 # The remote host
    PORT = 50007              # The same port as used by the server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))

    
    sendData(s, input)
    while 1:
        data = s.recv(1024)
        if not data:
            break

        sys.stdout.write(data)

    print 'shutting down/closing socket...'
    s.shutdown(2)
    s.close()
    del s

def get_raw_non_trivial_input():
    q = ''
    while not q:
        q = raw_input('>> ')

    return q

if __name__ == "__main__":
    while 1:
        q = get_raw_non_trivial_input()
        if q == 'quit':
            break

        get_reply(q)
