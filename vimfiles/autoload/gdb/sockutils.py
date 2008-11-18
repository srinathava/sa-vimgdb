def sendData(conn, data):
    # print 'seinding [%s]' % data
    data_len = len(data)
    total_sent = 0
    while total_sent < data_len:
        sent = conn.send(data[total_sent:])
        if sent == 0:
            raise RuntimeError, "Socket connection broken by client!"
        total_sent += sent

