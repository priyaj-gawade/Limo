#!/bin/bash
export NODE_ENV=production
export GENOFFICE_AUTOMATION_ENABLED=true
exec /usr/bin/xvfb-run -a --server-args='-screen 0 1024x768x24' /opt/limo/engines/office/node_modules/.bin/electron --no-sandbox /opt/limo/engines/office/apps/shell
