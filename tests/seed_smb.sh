#!/bin/bash

# Script to seed open-ssh server
echo "$(pwd)"
echo "Copying $1 to tests/bin/smb/$2"
mkdir -p tests/bin/smb/$2
cp -R $1 tests/bin/smb/$2
chmod -R 755 tests/bin/smb/$2
