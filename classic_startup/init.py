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
import nuke

# This covers initializing Toolkit for Nuke batch processes (nuke -t).
if not nuke.GUI:
    sys.path.append(os.path.dirname(__file__))

    try:
        import sgtk_startup
    finally:
        sys.path.pop()
