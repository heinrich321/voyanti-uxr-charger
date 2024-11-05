#!/usr/bin/with-contenv bashio
set -e

echo "Hello UXR"

# cd "${0%/*}"
cd /workdir
python3 -u ./app.py #"$@"