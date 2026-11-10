# network

VPC with one subnet, Cloud Router and Cloud NAT (outbound internet for VMs without external IPs, needed to reach the FIRMS API),
and a firewall rule that allows SSH and the Dagster UI port (3000) only from the IAP range (`35.235.240.0/20`) to instances tagged
`iap-access`. There is no public ingress.
