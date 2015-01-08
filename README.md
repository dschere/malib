Overview
==========================================================================================================

malib is a small python library that implements an application framework for mobile agents, 
that is code that is executed on foreign machines with a highly restricted execution environment. 
Within this restricted environment the mobile agent can do nothing other than call methods of
an api object. It can't import modules, access any I/O. It is restricted in how much memory it can
use, how much CPU time it can consume and the niceness of the child process it executes in.

As far as network transport there is a driver interface that allows the agents to hop from machine to
machine. The underlining mechanism can be anything the peer chooses. It is the goal to use libgnunet for
the network transport.




