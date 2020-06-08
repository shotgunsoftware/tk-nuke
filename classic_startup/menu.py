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

startup_path = os.path.dirname(__file__)
sys.path.append(startup_path)

# This covers initialization of Toolkit in GUI sessions of Nuke.
try:
    import sgtk_startup  # noqa
finally:
    # We can't just pop sys.path, because the sgtk_startup routine
    # might have run some code during bootstrap that appended to
    # sys.path.
    sys.path = [p for p in sys.path if p != startup_path]
