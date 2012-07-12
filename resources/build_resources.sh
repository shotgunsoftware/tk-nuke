#!/usr/bin/env bash
# 
# Copyright (c) 2008 Shotgun Software, Inc
# ----------------------------------------------------

echo "building user interfaces..."
pyside-uic --from-imports dialog.ui > ../python/tk_nuke/ui/dialog.py

echo "building resources..."
pyside-rcc resources.qrc > ../python/tk_nuke/ui/resources_rc.py
