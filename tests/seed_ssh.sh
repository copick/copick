#!/bin/bash

# Script to seed open-ssh server
sshpass -p "password" ssh -p 2222 -o "StrictHostKeyChecking=no" test.user@localhost "mkdir -p $2"
sshpass -p "password" scp -r -P 2222 -o "StrictHostKeyChecking=no" $1 test.user@localhost:$2
