# deploy_access

Permissions for the GitHub deploy service account to copy a package to one VM and install it: OS Login with sudo on that instance, the IAP
tunnel to that instance, permission to act as the VM's own service account, and read-only access to project metadata (needed by gcloud).
