#!/usr/bin/env python

import marshal
import socket
import struct
import traceback
import select

HDR_FORMAT=">I"

class Disconnect( RuntimeError ):
    pass

def sendMessage( s, obj ):
    payload = marshal.dumps(obj)
    packet = struct.pack(HDR_FORMAT,len(payload)) + payload
    s.sendall( packet )

def recvMessage( s ):
    def _getChunk(n):
        buf = ""
        while len(buf) < n:
            x = s.recv(n - len(buf))
            if x == "":                
                s.shutdown( socket.SHUT_RDWR ) 
                raise Disconnect, "Disconnected"     
            buf += x
        return buf
    hdr = _getChunk(struct.calcsize(HDR_FORMAT))        
    size = struct.unpack(HDR_FORMAT,hdr)[0]
    data = _getChunk( size )
    return marshal.loads( data )


class ApiIface:
    def __transaction(self, func, *args):
        sendMessage( self.s, (func,args) )
        return recvMessage( self.s )

    def __init__(self, rpcPort, eventPort ):
        # sequence matters here with the event port being connected
        # after the rpcPort, see peer._service_msg
        self.s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        self.s.connect( ('127.0.0.1',rpcPort) )

        self.e = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        self.e.connect( ('127.0.0.1',eventPort) )

        self.dispatch = {} 
 
    def register(self, event, cb, pri=0):
        if event not in self.dispatch:
            self.dispatch[event] = []
        self.dispatch[event].append( (cb,pri) )
        def sfunc( x, y ):  
            return cmp(y[1],x[1])
        self.dispatch[event].sort( sfunc ) 
            
    def unregister(self, event, cb ):
        if event in self.dispatch:
            def ff( x ):
                if x[0] == cb:
                    return 0
                return 1
            self.dispatch[event] = filter( ff, self.dispatch[event] )
      
    def listen(self, timeout=-1):
        r = select.select([self.e],[],[],timeout)
        if len(r) > 0:
            (event,args) = recvMessage( self.e )
            if event in self.dispatch:
                for (cb,pri) in self.dispatch[event]:
                    cb( *args )
        
    def __getattr__(self, name):
        class datalink:
            def __init__(self, func):
                self.func = func  
            def __call__(self, *args):
                return self.func( name, *args )  
        return datalink( self.__transaction )
        

def execute_agent_code( cobj, __api, __briefcase ):
    exec cobj

def sandbox( rpcPort, eventPort ):
    __api = ApiIface( rpcPort, eventPort )  

    # reuse the api event service to trap the init message 
    cfg = {'wait':True}
    def init( *args ):
        cfg['code'], cfg['briefcase'] = args 
        cfg['wait'] = False 
    __api.register("init",init)
    while cfg['wait']: 
        __api.listen(60)

    code = cfg['code']
    __briefcase = cfg['briefcase']

    bootstrap = \
"""
Api = __api
Briefcase = __briefcase
"""

    # compile the agent code 
    cobj = compile(bootstrap + code,"<string>","exec") 
 
    # prevent this process from performing any I/O outside
    # of using the api for communication.
    del socket.socket
    # no imports/IO allowed
    del __builtins__.__import__
    del __builtins__.open   

    # execute the agent code
    execute_agent_code( cobj, __api, __briefcase )

    

def test_server():
    import logging

    logging.basicConfig( filename="/dev/stdout", level=logging.DEBUG )

    class testApi:
        def log(self, severity, msg):
            getattr(logging,severity)( msg )

    api = testApi()
    code = \
"""
api.log('info','test briefcase=%s' % str(briefcase))
"""
    briefcase = {}
         

    rpc_s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)    
    rpc_s.bind( ('127.0.0.1',20000) )
    rpc_s.listen(1)

    evt_s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    evt_s.bind( ('127.0.0.1',20001) )
    evt_s.listen(1)

    connList = [rpc_s, evt_s]
    client = {}
    while True:
        ready, _p1, _p2 = select.select(connList,[],[],5)
        for r in ready:
            print r
            if r is rpc_s:
                conn, addr = rpc_s.accept()
                print "server accepting rpc connection "
                client['rpc'] = conn
                connList.append( conn )

            elif r is evt_s:
                conn, addr = evt_s.accept()

                print "server accepting event connection "

                client['evt'] = conn
                connList.append( conn )

                msg = ('init',(code,briefcase))
                print "sending ", msg 
                sendMessage( client['evt'], msg )       

            elif r is client.get('rpc',None):
                try:
                    meth,args = recvMessage( client['rpc'] )
                except Disconnect:
                    return
 
                print meth, args
                func = getattr(api,meth)
                r = func( *args )
                sendMessage( client['rpc'], r )

def create_agent_subprocess( rpcPort, eventPort ):
    """ Create a child process for executing the mobile
    """
    import subprocess     
    import inspect
    import sys
    import logging

    filename = inspect.getfile(inspect.currentframe())
    args = [sys.executable, filename, "agent", str(rpcPort), str(eventPort)]

    
    del sys
    del inspect

    logging.info("Executing '%s'" % ' '.join(args))
    return subprocess.Popen(args,close_fds=True,env={}) 

    
if __name__ == '__main__':
    import sys

    mode = sys.argv[1]
    if mode == "agent":
        rpcPort, eventPort = int(sys.argv[2]), int(sys.argv[3])
        sandbox( rpcPort, eventPort )
    elif mode == "test":
        test_server()
     
      
