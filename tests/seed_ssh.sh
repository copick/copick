#!/bin/bash

# Script to seed open-ssh server
sshpass -p "password" ssh -p 2222 -o "StrictHostKeyChecking=no" -o "UserKnownHostsFile=/dev/null" test.user@localhost "mkdir -p $2"
sshpass -p "password" scp -r -P 2222 -o "StrictHostKeyChecking=no" -o "UserKnownHostsFile=/dev/null" $1 test.user@localhost:$2
