# coding=utf-8

#  Copyright 2016 Andrei Fokau, Daniel Xu
#  
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#     http://www.apache.org/licenses/LICENSE-2.0
#  
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import datetime
import sys
import time
import threading
import traceback
import socketserver
import argparse
import codecs
import json
from dnslib import *

TTL = 60 * 5  # completely arbitrary TTL value
records = dict()
soa_records = dict()

class DomainName(str):
    def __getattr__(self, item):
        return DomainName(item + '.' + self)

class BaseRequestHandler(socketserver.BaseRequestHandler):

    def get_data(self):
        raise NotImplementedError

    def send_data(self, data):
        raise NotImplementedError

    def handle(self):
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
        print("\n\n%s request %s (%s %s):" % (self.__class__.__name__[:3], now, self.client_address[0],
                                               self.client_address[1]))
        try:
            data = self.get_data()
            self.send_data(dns_response(data))
        except Exception:
            traceback.print_exc(file=sys.stderr)


class TCPRequestHandler(BaseRequestHandler):

    def get_data(self):
        data = self.request.recv(8192).strip()
        sz = int(codecs.encode(data[:2], 'hex'), 16)
        if sz < len(data) - 2:
            raise Exception("Wrong size of TCP packet")
        elif sz > len(data) - 2:
            raise Exception("Too big TCP packet")
        return data[2:]

    def send_data(self, data):
        sz = codecs.decode(hex(len(data))[2:].zfill(4), 'hex')
        return self.request.sendall(sz + data)


class UDPRequestHandler(BaseRequestHandler):

    def get_data(self):
        return self.request[0].strip()

    def send_data(self, data):
        return self.request[1].sendto(data, self.client_address)

def build_fqdn_mappings(path):
    with open(path) as f:
        zone_file = json.load(f)

    for fqdn in zone_file['mappings']:
        for d in iter(fqdn.keys()):
            # this loop only runs once, kind of a hack to access the only key in the dict
            domain = DomainName(d)
            soa_record = SOA(
                mname=domain.ns1,     # primary name server
                rname=domain.apache,  # email of the domain administrator
                times=(
                    201307231,    # serial number (totally random ;)
                    60 * 60 * 1,  # refresh
                    60 * 60 * 3,  # retry
                    60 * 60 * 24, # expire
                    60 * 60 * 1,  # minimum
                )
            )
            print("adding domain: " + domain)
            records[domain] = [A(x) for x in fqdn[domain]] + [soa_record, NS(domain.ns1), NS(domain.ns2), MX(domain), CNAME(domain)]
            soa_records[domain] = soa_record

def dns_response(data):
    request = DNSRecord.parse(data)
    print(request)

    reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)
    qname = request.q.qname
    qn = str(qname)
    qtype = request.q.qtype
    qt = QTYPE[qtype]

    for domain, rrs in records.items():
        if domain == qn or qn.endswith('.' + domain):
        # we are the authoritative name server for this domain and all subdomains
            for rdata in rrs:
                # only include requested record types (ie. A, MX, etc)
                rqt = rdata.__class__.__name__
                if qt in ['*', rqt]:  
                    reply.add_answer(RR(rname=qname, rtype=getattr(QTYPE, str(rqt)), rclass=1, ttl=TTL, rdata=rdata))

            # add authoritative name servers to reply too
            # ns1 and ns1 are hardcoded in, change if necessary
            reply.add_auth(RR(rname=domain, rtype=QTYPE.NS, rclass=1, ttl=TTL, rdata=NS(domain.ns1)))
            reply.add_auth(RR(rname=domain, rtype=QTYPE.NS, rclass=1, ttl=TTL, rdata=NS(domain.ns2)))

            # add on the start of authority too, why not
            reply.add_auth(RR(rname=domain, rtype=QTYPE.SOA, rclass=1, ttl=TTL, rdata=soa_records[domain]))
            break

    print("---- Reply: ----\n", reply)

    return reply.pack()



if __name__ == '__main__':
    # handle cmd line args
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, help="port uDNS should listen on")
    parser.add_argument("zone_file", help="path to zone file")
    args = parser.parse_args()

    build_fqdn_mappings(args.zone_file)

    servers = [
        socketserver.ThreadingUDPServer(('localhost', args.port), UDPRequestHandler),
        socketserver.ThreadingTCPServer(('localhost', args.port), TCPRequestHandler),
    ]

    print("Starting nameserver...")
    for s in servers:
        thread = threading.Thread(target=s.serve_forever)  # that thread will start one more thread for each request
        thread.daemon = True  # exit the server thread when the main thread terminates
        thread.start()
    
    try:
        while 1:
            time.sleep(1)
            sys.stderr.flush()
            sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()
