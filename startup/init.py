# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
This file is loaded automatically by Nuke on startup (and file>new)

Note This file enable use tank engine in batch mode (nuke -t) to process automatic precomp, publish...
"""

import nuke
import os
import sys

def handle_new_tank_session():
    import tk_nuke
    tk_nuke.tank_ensure_callbacks_registered()

if not nuke.GUI:
    if not nuke.env.get("hiero"):
        # now we need to add our callback module to the pythonpath manually.
        # note! __file__ does not work for this file, so the engine passes
        # down the engine's python folder location to us via an env var.
        path = os.environ.get("TANK_NUKE_ENGINE_MOD_PATH")
        if path:
            sys.path.append(path)
            handle_new_tank_session()
        else:
            nuke.error("Shotgun could not find the environment variable TANK_NUKE_ENGINE_MOD_PATH!")




