"""
Allows for communication over a TCP link to be done using blowfish where the
data used to make the cyphers on both sides of the connection use temporary
RSA key pairs. After initialization the RSA keys are no longer needed and all
communication is done using symetrical encryption. 
"""

from Crypto.PublicKey import RSA
from Crypto import Random
from Crypto.Cipher import Blowfish
import uuid
import threading
import marshal
import struct
import socket
import logging
import traceback

class SecureLink:

    def __init__(self, name=None):
        self.send_cypher = None
        self.recv_cypher = None
        if name:
            self.name = name
        else:
            self.name = "noname_%ld" % id(self) 

    def send(self, conn, obj):
        
        payload = marshal.dumps( obj )
        (bf_key,iv) = self.send_cypher
        cipher = Blowfish.new(bf_key, Blowfish.MODE_CBC, iv)
        pad = "\000" * (8 - (len(payload) % 8))
        payload += pad
        e_payload = cipher.encrypt( payload )
 
        logging.debug("send: %d %d" % (len(e_payload), len(pad)))
        packet = struct.pack('>IB', len(e_payload), len(pad) ) + e_payload
        conn.sendall( packet )

    def recv(self, conn):
        def _get_chunk( size ):
            buf = "".encode()
            while len(buf) < size:
                x = conn.recv( size - len(buf) )
                if len(x) == 0:
                    raise socket.error, "Unexpect disconnect"    
                buf += x
            return buf

        hdr = _get_chunk( struct.calcsize('>IB') )
        logging.debug("recv: %s" % repr(hdr))
        (size,padsize) = struct.unpack('>IB', hdr)
        logging.debug("recv: %d %d" % (size, padsize))
        e_data = _get_chunk(  size )
        (bf_key,iv) = self.recv_cypher
        cipher = Blowfish.new(bf_key, Blowfish.MODE_CBC, iv)
        data = cipher.decrypt( e_data ) 
        return marshal.loads( data[:-padsize] )



    def _send(self, conn, obj):
        payload = marshal.dumps( obj )
        packet = struct.pack('>I',len(payload)) + payload
        conn.sendall( packet )


    def _recv(self, conn):
        def _get_chunk( size ):
            buf = "".encode()
            while len(buf) < size:
                x = conn.recv( size - len(buf) )
                if len(x) == 0:
                    raise socket.error, "Unexpect disconnect"    
                buf += x
            return buf
        hdr = _get_chunk( struct.calcsize('>I') )
        size = struct.unpack('>I', hdr)[0]
        data = _get_chunk( size )
        return marshal.loads( data )

        

    def setup(self, conn ):
        """
        create pub/priv/cipher

        send pub to other
        get pub from other

        encrypt our cipher with other_pub and send back
        receive other cipher and decrypt
        """

        logging.debug("entering setup")

        random_generator = Random.new().read
        # temporary key pair just to encyript the blowfish cyphers
        private_key = RSA.generate( 1024, random_generator )
        public_key = private_key.publickey()
        
        bs = Blowfish.block_size
        bf_key = uuid.uuid1().hex
        iv = Random.new().read(bs)

        # precalculated information for cypher   
        self.send_cypher = (bf_key,iv) 

        # send the our pubkey so the other peer can encrypt its
        # cipher information and send it to us.
        logging.debug("%s: exporting public key to remote host" % self.name)
        self._send( conn, public_key.exportKey() ) 

        # get the other's pubkey so we can encrypt our cipher
        # info.
        other_pub_key = RSA.importKey( self._recv(conn) )
        logging.debug("%s: sending cypher bf=%s iv=%s" % (self.name,bf_key,iv))
        self._send( conn, (other_pub_key.encrypt(bf_key,0),other_pub_key.encrypt(iv,0)) )
        
        (e_other_bf,e_other_iv) = self._recv( conn )
        logging.debug("%s: receiving cypher information" % self.name)
 
        other_bf = private_key.decrypt(e_other_bf)
        other_iv = private_key.decrypt(e_other_iv) 
        logging.debug("%s: receiving cypher bf=%s iv=%s" % (self.name,other_bf,other_iv))
        
        self.recv_cypher = (other_bf,other_iv)

        # each side now has an identical blowfish cypher for further communication.
        

def unittest():
    import thread, time
    logging.basicConfig( filename="/dev/stdout", level=logging.DEBUG )

    logging.debug( "unittest" )
 
    def test_server():
        logging.debug( "test_server" )
        
        s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        s.bind( ('',2115) )
        s.listen(5)
        (conn,saddr) = s.accept()
        sl = SecureLink()
        
        sl.setup( conn )
        logging.debug( "server received %s" % sl.recv( conn ) )
        conn.shutdown( socket.SHUT_RDWR )

    thread.start_new_thread( test_server, () )
    time.sleep(1)

    s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
     
    s.connect( ('',2115) )
    sl = SecureLink()
    sl.setup( s )
    sl.send( s, "hello again" )

    time.sleep(1) 
    s.shutdown( socket.SHUT_RDWR )

if __name__ == '__main__':
    unittest()
           
                

