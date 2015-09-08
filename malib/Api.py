import logging
from pubsub import pub
import thread
import socket
import p2pp
import struct
import threading
import Queue
import time
import traceback

HOST_AGENT      = 0
BROADCAST_EVENT = 1
POOL_CHECK_CONN_INTERVAL = 60
POOL_CONN_IDLE_TIME = 60

Logger = logging.getLogger('malib')

class _ConnectionPool( threading.Thread ):
    

    def __init__(self):
        threading.Thread.__init__(self)

        self.pool = {}
        self.msgq = Queue.Queue()
        self.next_conn_check = time.time() + POOL_CHECK_CONN_INTERVAL

    def shutdown(self):
        #    Sentinel value that is interpreted as a shutdown message.
        self.msgq.put((None,None))   

    def send(self, addr, msg):
        self.msgq.put( (addr,msg) )
        
    def run(self):
        Logger.info("Connection Pool thread started")
        try:
            self._run()
        except:
            Logger.error( traceback.format_exc() )
        Logger.info("Connection Pool thread closed")
               
                    

    # interval methods for this thread

    def _run(self):
        
        while True:
                       
            now = time.time() 
            if now > self.next_conn_check:
                Logger.info("checking open connections") 
                self._check_connections( now )          
                self.next_conn_check = now + POOL_CHECK_CONN_INTERVAL  

            try:
                (addr,msg) = self.msgq.get( timeout=2 )
            except Queue.Empty:
                Logger.info("empty queue") 
                continue
            Logger.info("msgq.get -> (%s,%s)" % (str(addr),str(msg)))

            # shutdown event  
            if addr == None and msg == None:
                break
            self._send( addr, msg )
        
         
        for (s,lastUsedTime,slink) in self.pool.values():    
            s.shutdown( socket.SHUT_RDWR )

    def _send( self, addr, msg ):
        if addr in self.pool:
            (s,lastUsedTime,slink) = self.pool[addr]
        else: 
            s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
            l_onoff = 1
            l_linger = 10
            s.setsockopt( socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', l_onoff, l_linger))
            try:
                s.connect( addr )
            except socket.error:
                Logger.warning("Connect failed for peer %s" % str(addr))
                pub.sendMessage("peer-connect-failed", addr=addr )
                return 
            s.settimeout(15) 
            slink = p2pp.SecureLink()
            slink.setup( s )

        try:
            slink.send( s, msg )
        except socket.error:
            Logger.warning("send failed for peer %s" % str(addr))
            pub.sendMessage("peer-send-failed", addr=addr )

        self.pool[addr]=(s,time.time(),slink)

    def _check_connections(self, now):
        for (addr, (s,lastTimeUsed,slink)) in self.pool.items():
             idle = now - lastTimeUsed
             if idle > POOL_CONN_IDLE_TIME:
                 try:
                     msg = (BROADCAST_EVENT,"ping",(),)                 
                     slink.send( s, msg )
                 except socket.error:
                     Logger.warning("test failed for peer %s" % str(addr))
                     pub.sendMessage("peer-send-failed", addr=addr )
                     try: 
                         s.shutdown( socket.SHUT_RDWR )     
                     except:
                         pass
                     del self.pool[addr]  


# Connection pool thread for manging open connections to peers.
ConnectionPool = _ConnectionPool()



def sendBroadcast( addr, event, *args):
    global  ConnectionPool

    msg = (BROADCAST_EVENT,event,args,)
    ConnectionPool.send( addr, msg )  

def sendAgent( addr, code, briefcase ):
    global  ConnectionPool

    msg = (HOST_AGENT,code,briefcase,)
    ConnectionPool.send( addr, msg )  

class MalibApiBase:
    """ Base class for mobile agents. Provides a facility for registering
        events, logging and sending mobile agents to other peers.
    """

    def addressIsAllowed(self, addr):
        return True

    def codeIsValid(self, code):
        return True  

    def log(self, severity, msg):
        if hasattr(logging,severity):
            getattr(logging,severity)(msg)
        else:
            Logger.error("unknown severity: " + msg)  
    
    def localBroadcast(self, event, *args ):
        pub.sendMessage("localBroadcast", event=event, args=args )

    def multicast(self, addrList, event, *args ):
        # send message to agents hosted locally
        pub.sendMessage("localBroadcast", event=event, args=args )
        # send to a list of remote hosts.
        for addr in addrList:
            thread.start_new_thread( sendBroadcast, (addr, event, args,) )  

    def sendAgent(self, code, briefcase ):
        thread.start_new_thread( sendAgent, (code, briefcase,) )


