import sandbox
import socket
import threading
import Queue
import select
import sys
import logging

class AgentController( threading.Thread ):
    """ 
       Uses 3 loopback sockets for IPC (this is platform neutral since windows
       only allows a select on a socket and doesn't support poll())

       One socket is used for IPC calls from the agent using the API calls
       an instance of the user supplied API object. This is the sole API
       that the agent can use. The socket binds to a random port and N number
       of agents use this socket for RPC calls to the api.

       Another socket is used to multicast events from the agent controller to
       agents. This forms a pub/sub model, again this is a server socket that
       services client connections from agents.

       The third socket is used as an alert utility since we can't select on 
       a message queue and a socket at the same time, I use a udp socket as
       an alert to instruct the agent controller that there is a inbound message.
    """
    def __init__(self, agentApi ):
        threading.Thread.__init__(self)

        self.agentApi = agentApi
        self.msgq = Queue.Queue()
        self.msgq_alert = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.msgq_alert.bind( ('127.0.0.1',0) )
        
        self.msgq_alert_port = self.msgq_alert.getsockname()[1]  
        self.connList = [self.msgq_alert]
        self.rpc_conn = set()
        self.evt_conn = set()
        self.agent_proc_list = []  
        self.running = True

    def shutdown(self):
        msg = (self._service_shutdown, ())
        self.msgq.put( msg )
        self.msgq_alert.sendto( "x", self.msgq_alert.getsockname() )
                  

    def hostTheAgent( self, code, breifcase ):
        rpcPort = self.rpc_s.getsockname()[1]
        evtPort = self.evt_s.getsockname()[1]           
        proc = sandbox.create_agent_subprocess( rpcPort, evtPort )
        self.agent_proc_list.append( proc ) 

        msg = (self._service_hostTheAgent, (code, breifcase))
        self.msgq.put( msg )         
        self.msgq_alert.sendto( "x", self.msgq_alert.getsockname() )

    def multicastEvent( self, eventId, *args ):
          
        msg = (self._service_multicastEvent, (eventId, args))
        self.msgq.put( msg )
        try:
            self.msgq_alert.sendto( "x", self.msgq_alert.getsockname() )
        except:
            if self.running:
                logging.error("unexpected broken pipe for msgq alert") 
        
    def _service_multicastEvent(self, eventId, argList ):
        for r in self.evt_conn:
            try:
                msg = (eventId,argList)
                sandbox.sendMessage( r, msg )
            except sandbox.Disconnect:
                self.evt_conn.remove( r )
                self.connList.remove( r )         
        
    def _service_shutdown(self):
        self.running = False  

    
    def _service_hostTheAgent(self, code, briefcase):
        "service incoming mobile agent" 
        initialized = False
        agent_comm = {}
        logging.info("host incoming agent")
        while not initialized:         
            ready, _p1, _p2 = select.select([self.rpc_s,self.evt_s],[],[],1)
            for r in ready:
                if r is self.rpc_s:
                    agent_comm['rpc'], _addr = self.rpc_s.accept()                
                    self.connList.append( agent_comm['rpc'] )
                elif r is self.evt_s:
                    agent_comm['evt'], _addr = self.evt_s.accept()                
                    self.connList.append( agent_comm['evt'] )
                    msg = ('init',(code,briefcase))
                    logging.info("sending agent the init message")
                    sandbox.sendMessage( agent_comm['evt'], msg )
                    initialized = True

        # lookup to facilitate rpc calls and events 
        self.rpc_conn.add( agent_comm['rpc'] )
        self.evt_conn.add( agent_comm['evt'] )
    
                     

    def _proc(self, timeout):
        ready, _p1, _p2 = select.select(self.connList,[],[],timeout)
        for r in ready:          
            if r is self.msgq_alert:   
                (data,_p3) = self.msgq_alert.recvfrom(1)      
                (func,args) = self.msgq.get()
                func( *args )
        
            elif r in self.rpc_conn:
                try:
                    meth,args = sandbox.recvMessage( r )
                except sandbox.Disconnect:
                    self.rpc_conn.remove( r )
                    self.connList.remove( r )
                    continue                    

                if hasattr(self.agentApi,meth):
                    func = getattr(self.agentApi,meth)
                    try: 
                        result = func( *args )
                    except:
                        result = {
                            'error': (str(sys.exc_type),str(sys.exc_value)) 
                        }
                else:
                    result = {
                        'error': ("<type 'exceptions.NameError'>","Unknown method '%s'" % meth)
                    }
                # return result back to waiting agent
                sandbox.sendMessage( r, result )
    


    def run(self):
        logging.info("agentController starting")   
        self.rpc_s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)    
        self.rpc_s.bind( ('127.0.0.1',0) )
        self.rpc_s.listen(1)

        self.evt_s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.evt_s.bind( ('127.0.0.1',0) )
        self.evt_s.listen(1)

        self.connList.append( self.rpc_s )
        self.connList.append( self.evt_s )

        while self.running:
            self._proc(5)

        # close all connections  
        for s in self.connList:
            try:
                s.shutdown( socket.SHUT_RDWR )
            except socket.error:
                pass
        
        # destroy agents
        for proc in self.agent_proc_list:
            try:
                proc.kill()
            except:
                pass   
        logging.info("agentController exiting")   

def unittest():
    import logging
    import Api
   
    logging.basicConfig( filename="/dev/stdout", level=logging.DEBUG )

    class TestApi( Api.MalibApiBase ):
        def test(self, *args):
            logging.info( str(args) )
        
    import time

    testApi = TestApi()
    ac = AgentController( testApi )
    ac.start()

    code = \
"""
running = True

def cb( *args ):
    global running
    global Api

    running = False
    Api.log("info","cb: " + str(args))

Api.register("help", cb)
Api.test("this is a test")

try:
    open("/tmp/test.txt","w").write("this should fail")
except:
    Api.log("info","open is disabled as expected")

while running:
    Api.listen(10)

Api.log("info","exiting")
"""
    briefcase = {}
    time.sleep( 1 )
    ac.hostTheAgent( code, briefcase )
    time.sleep( 1 )

    ac.multicastEvent( "help", 90 )
    time.sleep( 1 )

    ac.shutdown()

    
if __name__ == '__main__':
    unittest()

