""" 
Implements a restricted execution space for mobile agents. As 
a side effect it ignores SIGCHLD to prevent zombie processes.

"""
import api 
import os
import sys
import resource
import signal 
import logging

try:
    import cPickle as pickle
except:
    import pickle

def exec_cell( code, api ):
     # -----------------------------------------------------------------------
     __builtins__ = {}
     # __import__,open,eval,exec ... are now all dead the only library that is 
     # available is the one provided by the 'api' object. 
     exec(code)


     

class Agent( object ):
    limits = (
      (resource.RLIMIT_CPU, config.cpu_limits ),  
      (resource.RLIMIT_DATA, config.heap_limits ),

      # agent is not allowed direct file io of any kind
      (resource.RLIMIT_NOFILE, (0,0)) # No more files allowed open  
    )
    
    def __init__(self, handler ):
        self.handler = handler
        self.api_inst = AgentApi( vars(self.handler).keys(), os, pickle )

        self.bad_api_calls = [] 
        self.child_pid = None

        # ignore child exit code, prevent zombies
        signal.signal( signal.SIGCHLD, signal.SIG_IGN )

    def __del__(self):
        if self.child_pid:
            try:
                os.kill( self.child_pid, signal.SIGKILL )
            except OSError:
                pass

    def fileno(self):
        # needed to integrate with poll()
        return self.api_inst.control_recv.fileno()
    
    def shutdown(self):
        if self.child_pid > 0:
            try:
                os.kill( self.child_pid, signal.SIGKILL )
                os.waitpid( self.child_pid, 0 )
            except OSError:
                logging.error("agent.shutdown() failed")     

    def proc(self):
        # decode incoming message and execute handler method
        (funcname,args) = pickle.load( self.api_inst.control_recv )
        logging.debug("agent.proc() received (%s,%s)" % (funcname,str(args)))
        if hasattr(self.handler,funcname):           
            func = getattr(self.handler,funcname)
            try:
                answer = func( *args )
            except:
                # caller is untrusted, count the number
                answer = (-1,None)
                self.bad_api_calls.append( sys.exc_type )
        else:     
            answer = (-1,None)
            self.bad_api_calls.append( NameError )
        logging.debug("agent.proc() responded %s" %  str(answer) )
        pickle.dump( self.api_inst.control_send, answer )


    def launch_untrused(self, code):
        """ Launches untrusted code in a sandboxed child process
            o resource limits
            o __builtins__ restricted just to an api specifed
              by the 'handler' object.
        """
        pid = os.fork()
        if pid == 0:
            r = 0
 
            # enforce limits on this child process, does not affect
            # existing file handles
            for (resId, (s_limit,h_limit)) in self.limits:
                resource.setrlimit( resId, s_limit, h_limit )
            # builtins get blown away after this point
            try:
                exec_cell( code, self.api_inst )
            except:
                r = -1
                self.api_inst.unhandled_exception( traceback.format_exc() ) 
            sys.exit(r) 
        else:
            self.child_pid = pid
                 
             
       
            
