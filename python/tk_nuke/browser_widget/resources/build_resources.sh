#!/usr/bin/env bash
# 
# Copyright (c) 2008 Shotgun Software, Inc
# ----------------------------------------------------

echo "building user interfaces..."
pyside-uic --from-imports header.ui > ../ui/header.py
pyside-uic --from-imports item.ui > ../ui/item.py
pyside-uic --from-imports browser.ui > ../ui/browser.py

echo "building resources..."
pyside-rcc resources.qrc > ../ui/resources_rc.py
