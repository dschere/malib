""" Agent side api which hides the implementation behind pipes.  
"""

class AgentApi( object ):
    def __init__(self, methods, os, pickle):
        self.fd_list = []
        self.methods = methods

        fd_r, fd_w = os.pipe()
        self.fd_list += [fd_r, fd_w]        
 
        self.agent_recv = os.fdopen(fd_r,'r')
        self.control_send = os.fdopen(fd_w,'w')
        
        fd_r, fd_w = os.pipe()
        self.fd_list += [fd_r, fd_w]        

        self.control_recv = os.fdopen(fd_r,'r')
        self.agent_send = os.fdopen(fd_w,'w')

        self.enc_snd = pickle.dump
        self.dec_rcv = pickle.load

        self.resLimit = None

        import signal
        if hasattr(signal,'SIGXCPU'):
            class h:
                def __init__(self, p):
                    self.p = p
                def __call__(self, *arg):
                    if self.p.resLimit != None:
                        self.p.resLimit() 
            signal.signal( signal.SIGXCPU, h(self) )
        


    def listen(self):
        return self.dec_rcv( self.agent_recv )

    def __getattr__(self, n):

        "Proxy methods which forward the command to the controller "
        class proxy_method:
            def __init__(self, n, x):
                self.n = n
                self.x = x
            def __call__(self, *args):
                self.x.enc_snd( (self.n,args), self.x.agent_send )
                self.x.agent_send.flush()
                return self.x.dec_rcv( self.agent_recv )
                 
        if n in self.methods:
            return proxy_method( n, self )
         

