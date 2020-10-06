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

# Disable the importing of the web engine widgets submodule from PySide2
# if this is a Windows environment. Failing to do so will cause Nuke to freeze on startup.
nuke_version = (
    nuke.env.get("NukeVersionMajor"),
    nuke.env.get("NukeVersionMinor"),
    nuke.env.get("NukeVersionRelease"),
)

if nuke_version[0] > 10 and sys.platform.startswith("win"):
    print(
        "Nuke 11+ on Windows can deadlock if QtWebEngineWidgets "
        "is imported. Setting SHOTGUN_SKIP_QTWEBENGINEWIDGETS_IMPORT=1..."
    )
    os.environ["SHOTGUN_SKIP_QTWEBENGINEWIDGETS_IMPORT"] = "1"

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
