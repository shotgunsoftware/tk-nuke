# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sys
import nuke

# This covers initializing Toolkit for Nuke batch processes (nuke -t).
# Since Nuke 11, Nuke appears to call the init.py script multiple times on start up. The first time it calls it, the
# nuke.GUI returns true (if we genuinely are in a GUI session), but the subsequent runs of this script yield False
# which means it tries to bootstrap again and again. To get around this, we set an environment var on the first time
# it's called and then in use it to check and block subsequent bootstraps. This env var is not used anywhere else.
if not os.environ.get("SHOTGUN_INIT_RUN"):
    os.environ["SHOTGUN_INIT_RUN"] = "1"

    if not nuke.GUI:
        startup_path = os.path.dirname(__file__)
        sys.path.append(startup_path)
        try:
            # importing sgtk_startup is enough to trigger the bootstrap process
            import sgtk_startup
        finally:
            # We can't just pop sys.path, because the sgtk_startup routine
            # might have run some code during bootstrap that appended to
            # sys.path.
            sys.path = [p for p in sys.path if p != startup_path]
