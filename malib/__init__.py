from pubsub import pub
import peer
import logging
import config

__PeerInst = None

def PeerStart( api=None, cfg={} ):
    global __PeerInst

    if api:
        __PeerInst = peer.Peer( api )
        for k,v in cfg.items():
            if hasattr(config,k):
                logging.info("changing %s from %s to %s\n" %(k,getattr(config,k),v)) 
                setattr(config,k,v)

        # setup malib logger
        peer.setup_logger()      

        # launch peer thread
        __PeerInst.start()
    else:
        raise ValueError, "Inside malib-start: api must be defined" 

def PeerStop():
    global __PeerInst

    if __PeerInst:
        __PeerInst.stop()          

pub.subscribe( PeerStart, "malib-start" )
pub.subscribe( PeerStop , "malib-stop"  )

