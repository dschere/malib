import agentController
import config
import p2pp
import SocketServer
import socket
import threading
import Api
import logging
import traceback
from pubsub import pub

Logger = logging.getLogger('malib')


class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def onShutdown(self):
        try:
            self.request.shutdown( socket.SHUT_RDWR ) 
        except:
            pass 
        self.running = False

    def setup(self):
        pub.subscribe(self.onShutdown, "sys-shutdown")
        self.running = True
        self.sl = p2pp.SecureLink()
        self._addr = self.request.getsockname()
  
        allowed = True
        if hasattr(self.api,"addressIsAllowed"):
            if not self.api.addressIsAllowed( self._addr ):
                allowed = False
        if allowed:
            Logger.info("calling sl.setup on %s" % str(self.request.getsockname()))
            self.sl.setup( self.request )
            Logger.info("setup complete")
        else:
            self.request.shutdown( socket.SHUT_RDWR ) 

    def _handle_host_agent(self, code, briefcase):
        valid = True
        if hasattr(self.api,"codeIsValid"):        
            if not self.api.codeIsValid( code ):
                valid = False
                Logger.warning("codeIsValid failed") 

        if valid:
            self.agentCtrl.hostTheAgent( code, briefcase )

    def _handle(self):        
        try: 
            args = self.sl.recv( self.request )
        except socket.error:
            return
  
        Logger.debug("handle request %s" % str(args)) 
        msgType = args[0]
        
        if msgType == Api.HOST_AGENT:
            _p1, code, briefcase = args
            self._handle_host_agent( code, briefcase )
        elif msgType == Api.BROADCAST_EVENT:
            _p1, event, evt_args = args
            self.agentCtrl.multicastEvent( event, *evt_args )
        else:
            Logger.error("Unknown message type %s" % str(msgType)) 

    def handle(self):        
        try:
            while self.running:
                self._handle()
        except:
            Logger.error( traceback.format_exc() )     
            

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


class Peer:

    def __init__(self, api):
        self.agentCtrl = agentController.AgentController( api )
        self.api = api

    def start(self):
        # start connection pool  
        Api.ConnectionPool.start() 

        ThreadedTCPRequestHandler.api = self.api
        ThreadedTCPRequestHandler.agentCtrl = self.agentCtrl

        self.agentCtrl.start()
        addr = (config.BindHost, config.BindPort)  

        ThreadedTCPServer.allow_reuse_address = True

        server = ThreadedTCPServer(addr, ThreadedTCPRequestHandler)
        server.request_queue_size = config.PeerRequestQueueSize

        #ip, port = server.server_address

        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        server_thread = threading.Thread(target=server.serve_forever)
        # Exit the server thread when the main thread terminates
        server_thread.daemon = True
        server_thread.start()

        self.server = server
        self.server_thread = server_thread

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.agentCtrl.shutdown()
        Api.ConnectionPool.shutdown() 

        Logger.info("joining threading waiting for exit")
        # close client socket connections
        pub.sendMessage("sys-shutdown")

        Api.ConnectionPool.join()
        self.agentCtrl.join()        
        self.server_thread.join()
        Logger.info("done") 
        

def unittest( peer ):

    class TestApi( Api.MalibApiBase ):
        def test(self, *args):
            Logger.info( str(args) )
        
    import time

    testApi = TestApi()

    code = \
"""
running = True

def cb( *args ):
    global running
    global Api

    running = False
    Api.log("info","cb: " + str(args))

Api.register("help", cb)
Api.log("info","--------- this is a test")

try:
    open("/tmp/test.txt","w").write("this should fail")
except:
    Api.log("info","open is disabled as expected")

try:
    while running:
        Api.listen(10)
except:
    pass 

Api.log("info","exiting startup test")
"""
    briefcase = {}
    
    addr = (config.BindHost, config.BindPort)
    Api.sendAgent( addr, code, briefcase )
    #time.sleep(1)
    Api.sendBroadcast( addr, "help", 90 )


def setup_logger():
    # create logger with 'spam_application'
    logger = logging.getLogger('malib')
    lvl = getattr(logging, config.LogLevel.upper() )  
    logger.setLevel(lvl)

    # create file handler which logs even debug messages
    fh = logging.FileHandler( config.LogFile )
    fh.setLevel(lvl)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(lvl)

    # create formatter and add it to the handlers
    fmt = "%(asctime)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s"  
    formatter = logging.Formatter(fmt)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        def change_config( **args ):
            for (k,v) in args.items():
                sys.stdout.write("changing %s from %s to %s\n" %(k,getattr(config,k),v)) 
                setattr(config,k,v)
        eval("change_config( %s )" % sys.argv[1])

    setup_logger()
    
    api = Api.MalibApiBase()
    p = Peer( api )
    p.start()
    unittest(p)
    print "press any key to exit", raw_input()
    p.stop()
    
