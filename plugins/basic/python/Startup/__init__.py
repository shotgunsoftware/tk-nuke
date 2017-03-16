# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
This file is being imported by Nuke Studio automatically because it is in the NUKE_PATH.
It launches the plugin's bootstrap process by reuning the one for Nuke.
"""

import imp
import uuid
import os
import inspect


def startup():
    """
    Reuses the Nuke way of starting up.
    """
    startup_root_path = os.path.dirname(__file__)
    module = None
    try:
        module = imp.load_source(
            uuid.uuid4().hex,
            os.path.normpath(os.path.join(startup_root_path, "..", "..", "menu.py"))
        )
    finally:
        if module:
            del module


startup()
