uDNS
=====

uDNS is a small DNS server that takes in a pre-defined set of FQDN and the IPs that the FQDN maps to. The mappings should be inputted with a JSON file in a format described below.

uDNS runs on localhost and serves whatever port is specified in the command line arguments. uDNS serves both UDP and TCP connections.


JSON format
------
### The canonical format is as follows:
```json
{
  "mappings": [
    {"fqdn1": ["ip1", "ip2", "etc"]},
    {"fqdn2": ["ip3", "ip4", "etc"]},
    {"fqdn3": ["ip5"]},
    {...}
  ]
}
```

An example can be found in `sample_zonefile.json`


Running
------
`python3 uDNS.py port zone_file`
