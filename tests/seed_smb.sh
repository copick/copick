#!/bin/bash

# Script to seed open-ssh server
#echo "$(pwd)"
#echo "Copying $1 to tests/bin/smb/$2"
mkdir -p tests/bin/smb/$2
cp -R $1 tests/bin/smb/$2
chmod -R 775 tests/bin/smb/$2
# Need to grant ownership to smbuser:smb for some tests to work (permission issues), otherwise owned by root if copied
# from host
docker compose -f ./tests/docker-compose.yml --profile smb exec -T smb-server sh -c "chown -R smbuser:smb /share/data/$2"
